# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "pandas", "geopandas", "shapely", "pyproj", "pillow", "scipy", "scikit-learn", "lxml"]
# ///
"""Build the POC store the API serves: regional rasters, per-field COG/PNG, stats,
confidence and a SQLite DB. Uses only files already in data/seggerde/ (no downloads).

    uv run poc/build_store.py          # from the repo root; rebuilds poc/store/ from scratch
    uv run poc/validate.py             # then refill the `validation` table and poc/VALIDATION.md

Inputs
- data/seggerde/clean/fields_clean.geojson        87 fields
- data/seggerde/soilgrids/s2grid/*.tif            SoilGrids v2.0 on the S2 10 m grid, quantile bands
- data/seggerde/nibis/raw/gfi_L849_*.json         Bodenschätzung parcels (polygons) at each field's sample point
- data/seggerde/nibis/nibis_fields.csv            NIBIS coverage share per field (west = Niedersachsen)
- data/seggerde/sentinel2/relative_productivity.tif, yield_potential_zones.tif

Outputs (poc/store/)
- soil.sqlite                                     schema in poc/schema.sql
- runs/<run_id>/regional/<param>__<source>.tif    farm-wide, EPSG:32632 10 m, bands value/lo90/hi90/confidence
- runs/<run_id>/fields/<plotId>/<param>__<source>.tif / .png / __conf.png
- runs/<run_id>/covariates/dem__copernicus.tif   model inputs, not API layers: elev, slope, twi, rel_elev, ground_mask
- poc/samples/request.json, response.json         example request and the response the API must return
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
import warnings
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.shutil
from PIL import Image
from rasterio.features import rasterize
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window, from_bounds
from shapely import affinity
from shapely.geometry import box, mapping, shape

from lib import yield_model as ym
from lib.dem import terrain
from lib.derived_soil import bodenzahl_model, buek_unit_raster, calibrate_texture, unit_nfk

warnings.filterwarnings("ignore", category=RuntimeWarning)  # nanmean of empty slices

ROOT = Path(__file__).resolve().parents[1]
SEG = ROOT / "data" / "seggerde"
POC = ROOT / "poc"
STORE = POC / "store"
RUN_ID = "poc-2026-10-03"
RUN_DIR = STORE / "runs" / RUN_ID
YIELD_META: dict = {}
DERIVED_META: dict = {}

UTM = "EPSG:32632"
PNG_GROUND_RES_M = 2.5  # PNG pixel size on the ground; nearest-neighbour, so 10 m blocks stay crisp
Z90 = 1.645

# Confidence codes stored in band 4 of every raster
LOW, MEDIUM, HIGH = 1, 2, 3
LEVEL_NAME = {LOW: "low", MEDIUM: "medium", HIGH: "high"}

SOILGRIDS_TOPSOIL = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
SOILGRIDS_ROOTZONE = {"0-5cm": 50, "5-15cm": 100, "15-30cm": 150, "30-60cm": 300, "60-100cm": 400}  # mm

BODENART = {  # Bodenschätzung soil class (first token of Klassenzeichen)
    "S": ("Sand", "#f6e8c3"), "Sl": ("anlehmiger Sand", "#ecd59a"), "lS": ("lehmiger Sand", "#dfc27d"),
    "SL": ("stark lehmiger Sand", "#c9a25a"), "sL": ("sandiger Lehm", "#a6763c"), "L": ("Lehm", "#80cdc1"),
    "LT": ("schwerer Lehm", "#35978f"), "T": ("Ton", "#01665e"), "Mo": ("Moor", "#543005"),
}
BODENART_CODES = list(BODENART)

COLORMAPS = {
    "ph": {"type": "continuous", "unit": "pH", "stops": [[4.5, "#a50026"], [5.0, "#f46d43"], [5.5, "#fee08b"], [6.0, "#d9ef8b"], [6.5, "#66bd63"], [7.5, "#006837"]]},
    "clay": {"type": "continuous", "unit": "%", "stops": [[0, "#fff7bc"], [5, "#fee391"], [10, "#fec44f"], [15, "#fe9929"], [20, "#ec7014"], [30, "#8c2d04"]]},
    "soc": {"type": "continuous", "unit": "g/kg", "stops": [[10, "#f7fcf0"], [20, "#ccebc5"], [30, "#7bccc4"], [40, "#2b8cbe"], [60, "#084081"]]},
    "nfk": {"type": "continuous", "unit": "mm", "stops": [[50, "#f7fbff"], [100, "#c6dbef"], [150, "#6baed6"], [200, "#2171b5"], [300, "#08306b"]]},
    "bodenzahl": {"type": "continuous", "unit": "points", "stops": [[10, "#a50026"], [20, "#f46d43"], [30, "#fee08b"], [45, "#a6d96a"], [60, "#1a9850"], [80, "#006837"]]},
    "yield_potential": {"type": "diverging", "unit": "index (field mean = 100)", "center": 100, "stops": [[80, "#a50026"], [90, "#f46d43"], [97, "#fee08b"], [100, "#ffffbf"], [103, "#d9ef8b"], [110, "#66bd63"], [120, "#006837"]]},
    "bodenart": {"type": "categorical", "unit": "class", "classes": [{"value": i + 1, "code": c, "label": BODENART[c][0], "color": BODENART[c][1]} for i, c in enumerate(BODENART_CODES)]},
}

PARAMETERS = [
    ("texture", "Soil texture", "Clay content 0–30 cm (SoilGrids) or Bodenart class (Bodenschätzung)"),
    ("ph", "pH (H2O)", "Topsoil pH 0–30 cm"),
    ("soc", "Soil organic carbon", "Topsoil SOC 0–30 cm"),
    ("nfk", "Plant-available water (nFK)", "Available water capacity 0–100 cm"),
    ("bodenzahl", "Bodenzahl", "Official soil quality score 0–100 (Bodenschätzung)"),
    ("yield_potential", "Yield potential", "Relative index, 100 = field mean; from multi-year Sentinel-2 peak NDVI"),
]

SOURCES = [
    ("soilgrids", "ISRIC SoilGrids v2.0", "250 m grid", 250, "global", "CC BY 4.0", "2026-10-03"),
    ("lbeg_bk50", "LBEG BK50 (NIBIS)", "1:50 000", None, "Niedersachsen", "not verified", "2026-10-03"),
    ("lbeg_bodenschaetzung", "LBEG Bodenschätzung (NIBIS)", "1:5 000", None, "Niedersachsen", "not verified", "2026-10-03"),
    ("derived", "Own model (Sentinel-2 L2A, 2019–2026)", "10 m grid", 10, "farm", "Copernicus open data", "2026-10-03"),
]

# Which source can deliver which parameter. Anything not listed is `not_applicable`.
SOURCE_PARAMETERS = [
    ("soilgrids", "texture", "Clay % (Q0.5), depth-weighted 0–30 cm; sand/silt and USDA class in stats"),
    ("soilgrids", "ph", "phh2o Q0.5, depth-weighted 0–30 cm"),
    ("soilgrids", "soc", "soc Q0.5, depth-weighted 0–30 cm"),
    ("soilgrids", "nfk", "Sum over 0–100 cm of (wv0033 − wv1500) × layer thickness"),
    ("lbeg_bk50", "nfk", "nFKWe exists in BK50 but was not in the downloaded attributes"),
    ("lbeg_bodenschaetzung", "texture", "Bodenart from Klassenzeichen (categorical)"),
    ("lbeg_bodenschaetzung", "bodenzahl", "BODENZ of each parcel"),
    ("derived", "nfk", "nFKWe of the BÜK200 unit (nearest sample point): KA5 lookup over its agricultural "
                       "profiles, area-weighted; approximate KA5 values"),
    ("derived", "bodenzahl", "Model trained on the downloaded Bodenschätzung parcels (west), applied farm-wide"),
    ("derived", "yield_potential", "yield_v1: water-scaled multi-year relative peak NDVI (normal spring) blended "
                                   "with a soil/terrain model; rescaled to field mean = 100"),
]


# ---------------------------------------------------------------- helpers

def hex_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def colorize(values: np.ndarray, cmap: dict) -> np.ndarray:
    """RGBA uint8 image; NaN → transparent. Continuous maps interpolate linearly between stops."""
    rgba = np.zeros(values.shape + (4,), np.uint8)
    valid = np.isfinite(values)
    if cmap["type"] == "categorical":
        for c in cmap["classes"]:
            m = valid & (values == c["value"])
            rgba[m, :3] = hex_rgb(c["color"])
            rgba[m, 3] = 255
        return rgba
    xs = [s[0] for s in cmap["stops"]]
    cols = np.array([hex_rgb(s[1]) for s in cmap["stops"]], float)
    v = np.clip(values[valid], xs[0], xs[-1])
    for ch in range(3):
        rgba[valid, ch] = np.interp(v, xs, cols[:, ch]).round().astype(np.uint8)
    rgba[valid, 3] = 255
    return rgba


def hatch(conf: np.ndarray) -> np.ndarray:
    """RGBA overlay: diagonal dark hatch on low-confidence pixels, transparent elsewhere."""
    rows, cols = np.indices(conf.shape)
    stripe = ((rows + cols) % 8) < 2
    rgba = np.zeros(conf.shape + (4,), np.uint8)
    m = (conf == LOW) & stripe
    rgba[m] = (30, 30, 30, 190)
    return rgba


def band(path: Path, name: str) -> np.ndarray:
    with rasterio.open(path) as r:
        return r.read(r.descriptions.index(name) + 1).astype("float32")


def usda_class(sand: float, silt: float, clay: float) -> str:
    tot = sand + silt + clay
    sand, silt, clay = (100 * x / tot for x in (sand, silt, clay))
    if silt + 1.5 * clay < 15:
        return "sand"
    if silt + 2 * clay < 30:
        return "loamy sand"
    if (7 <= clay < 20 and sand > 52) or (clay < 7 and silt < 50):
        return "sandy loam"
    if 7 <= clay < 27 and 28 <= silt < 50 and sand <= 52:
        return "loam"
    if (silt >= 50 and 12 <= clay < 27) or (50 <= silt < 80 and clay < 12):
        return "silt loam"
    if silt >= 80 and clay < 12:
        return "silt"
    if 20 <= clay < 35 and silt < 28 and sand > 45:
        return "sandy clay loam"
    if 27 <= clay < 40 and 20 < sand <= 45:
        return "clay loam"
    if 27 <= clay < 40 and sand <= 20:
        return "silty clay loam"
    if clay >= 35 and sand > 45:
        return "sandy clay"
    if clay >= 40 and silt >= 40:
        return "silty clay"
    return "clay"


def geom_hash(geom) -> str:
    """Stable hash of a lon/lat geometry, coordinates rounded to ~0.1 m."""
    def rnd(c):
        return [rnd(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(c[0], 6), round(c[1], 6)]
    g = mapping(geom)
    return hashlib.sha1(json.dumps({"type": g["type"], "coordinates": rnd(g["coordinates"])}).encode()).hexdigest()[:16]


def r(x, nd=2):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def write_cog(path: Path, arr: np.ndarray, transform, names: list[str], tags: dict, **cog_opts):
    path.parent.mkdir(parents=True, exist_ok=True)
    profile = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0],
                   dtype="float32", crs=UTM, transform=transform, nodata=float("nan"))
    with MemoryFile() as mem:
        with mem.open(**profile) as dst:
            dst.write(arr.astype("float32"))
            for i, n in enumerate(names, 1):
                dst.set_band_description(i, n)
            dst.update_tags(**{k: str(v) for k, v in tags.items()})
        with mem.open() as src:
            rasterio.shutil.copy(src, path, driver="COG", compress="DEFLATE", predictor=3, overview_resampling="nearest", **cog_opts)


# ---------------------------------------------------------------- regional layers

def load_grid():
    with rasterio.open(SEG / "sentinel2" / "relative_productivity.tif") as src:
        return src.transform, src.height, src.width


def soilgrids_layer(prop: str, depths: dict[str, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Depth-weighted Q0.5 and an approximate 90 % range (layers treated as fully correlated)."""
    path = SEG / "soilgrids" / "s2grid" / f"{prop}.tif"
    tot = sum(depths.values())
    q = {s: sum(band(path, f"{d}_{s}") * w for d, w in depths.items()) / tot for s in ("Q0.05", "Q0.5", "Q0.95")}
    return q["Q0.5"], q["Q0.05"], q["Q0.95"]


def soilgrids_nfk() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """nFK 0–100 cm in mm from field capacity − wilting point (vol %), σ from the quantiles."""
    fc_p, wp_p = SEG / "soilgrids" / "s2grid" / "wv0033.tif", SEG / "soilgrids" / "s2grid" / "wv1500.tif"
    val = np.zeros(1, "float32")
    sig = np.zeros(1, "float32")
    for d, mm in SOILGRIDS_ROOTZONE.items():
        fc, wp = band(fc_p, f"{d}_Q0.5"), band(wp_p, f"{d}_Q0.5")
        s_fc = (band(fc_p, f"{d}_Q0.95") - band(fc_p, f"{d}_Q0.05")) / 3.29
        s_wp = (band(wp_p, f"{d}_Q0.95") - band(wp_p, f"{d}_Q0.05")) / 3.29
        val = val + (fc - wp) / 100 * mm
        sig = sig + np.sqrt(s_fc ** 2 + s_wp ** 2) / 100 * mm
    return val, np.maximum(val - Z90 * sig, 0), val + Z90 * sig


def nanmedian3(a: np.ndarray) -> np.ndarray:
    p = np.pad(a, 1, constant_values=np.nan)
    win = np.lib.stride_tricks.sliding_window_view(p, (3, 3))
    out = np.nanmedian(win.reshape(a.shape + (9,)), axis=-1)
    return np.where(np.isfinite(a), out, np.nan).astype("float32")


def soil_confidence(param: str, val, lo, hi) -> np.ndarray:
    """SoilGrids is one coarse source, so medium at best; low where the range crosses the decision line."""
    conf = np.full(val.shape, MEDIUM, "float32")
    if param == "ph":
        conf[(lo < 5.5) & (hi > 5.5)] = LOW            # liming threshold
    elif param == "texture":
        conf[(hi - lo) > 10] = LOW                      # range wider than one texture class (~10 % clay)
    elif param == "soc":
        conf[(hi - lo) > 0.5 * val] = LOW
    elif param == "nfk":
        conf[((lo < 90) & (hi > 90)) | ((lo < 140) & (hi > 140))] = LOW  # irrigation-relevant classes
    conf[~np.isfinite(val)] = np.nan
    return conf


def load_bodenschaetzung() -> gpd.GeoDataFrame:
    rows = {}
    for p in sorted((SEG / "nibis" / "raw").glob("gfi_L849_*.json")):
        for f in json.loads(p.read_text()).get("features", []):
            if not f.get("geometry"):
                continue
            pr = f["properties"]
            geom = affinity.translate(shape(f["geometry"]), xoff=-32_000_000)  # strip the "32" zone prefix
            bodenart = (pr.get("KLASSENZEICHEN_SEP") or "").split(";")[0] or None
            rows[pr["FL_NR"]] = dict(parcel_id=pr["FL_NR"], bodenzahl=pr.get("BODENZ"), ackerzahl=pr.get("ACKERZ"),
                                     klassenzeichen=pr.get("KLASSENZEICHEN"), bodenart=bodenart,
                                     updated=pr.get("UP_DATE"), geometry=geom)
    return gpd.GeoDataFrame(list(rows.values()), crs="EPSG:25832").to_crs(UTM)


def build_regional(transform, h, w, parcels):
    out = {}  # (param, source) -> dict(value, lo, hi, conf, kind, cmap, unit, zone_m)
    for param, prop, cmap, unit in [("texture", "clay", "clay", "% clay"), ("ph", "phh2o", "ph", "pH"), ("soc", "soc", "soc", "g/kg")]:
        v, lo, hi = soilgrids_layer(prop, SOILGRIDS_TOPSOIL)
        out[(param, "soilgrids")] = dict(value=v, lo=lo, hi=hi, conf=soil_confidence(param, v, lo, hi),
                                         kind="continuous", cmap=cmap, unit=unit, zone_m=20, native_m=250)
    v, lo, hi = soilgrids_nfk()
    out[("nfk", "soilgrids")] = dict(value=v, lo=lo, hi=hi, conf=soil_confidence("nfk", v, lo, hi),
                                     kind="continuous", cmap="nfk", unit="mm", zone_m=20, native_m=250)
    # sand / silt kept for texture stats
    out["_sand"] = soilgrids_layer("sand", SOILGRIDS_TOPSOIL)[0]
    out["_silt"] = soilgrids_layer("silt", SOILGRIDS_TOPSOIL)[0]

    # Bodenschätzung: rasterise the downloaded parcels. Official 1:5k survey → high where present.
    shp = (h, w)
    bz = rasterize(((g, v) for g, v in zip(parcels.geometry, parcels.bodenzahl) if v is not None),
                   out_shape=shp, transform=transform, fill=np.nan, dtype="float32")
    ba = rasterize(((g, BODENART_CODES.index(c) + 1) for g, c in zip(parcels.geometry, parcels.bodenart) if c in BODENART),
                   out_shape=shp, transform=transform, fill=np.nan, dtype="float32")
    sigma_bz = 3.0  # assumed until calibrated: Bodenzahl ±5 points at 90 %
    out[("bodenzahl", "lbeg_bodenschaetzung")] = dict(
        value=bz, lo=bz - Z90 * sigma_bz, hi=bz + Z90 * sigma_bz, conf=np.where(np.isfinite(bz), HIGH, np.nan).astype("float32"),
        kind="continuous", cmap="bodenzahl", unit="points", zone_m=20, native_m=None)
    out[("texture", "lbeg_bodenschaetzung")] = dict(
        value=ba, lo=np.full(shp, np.nan, "float32"), hi=np.full(shp, np.nan, "float32"),
        conf=np.where(np.isfinite(ba), HIGH, np.nan).astype("float32"),
        kind="categorical", cmap="bodenart", unit="class", zone_m=20, native_m=None)

    return out


NFK_LOOKUP_SIGMA_MM = 30 / Z90   # ±30 mm at 90 % for the approximate KA5 lookup itself


def apply_texture_calibration(layers, parcels, transform, h, w) -> dict:
    """Replace SoilGrids' own clay interval with the error measured against Bodenschätzung (west)."""
    pid = rasterize(((g, i + 1) for i, g in enumerate(parcels.geometry)), out_shape=(h, w), transform=transform,
                    fill=0, dtype="int32")
    L = layers[("texture", "soilgrids")]
    cal = calibrate_texture(L["value"], layers[("texture", "lbeg_bodenschaetzung")]["value"], pid, BODENART_CODES)
    L["lo"] = np.maximum(L["value"] - Z90 * cal["rmse"], 0)
    L["hi"] = L["value"] + Z90 * cal["rmse"]
    L["conf"] = soil_confidence("texture", L["value"], L["lo"], L["hi"])
    L["calibrated"] = True
    (RUN_DIR / "covariates" / "calibration.json").write_text(json.dumps(dict(texture_soilgrids=cal), indent=1))
    return cal


def build_derived_soil(layers, dem, buek, parcels, fall, transform, h, w):
    """Derived nFK (BÜK200 unit → KA5) and Bodenzahl (model trained on the west). Returns metadata."""
    units = unit_nfk(SEG / "raw" / "buek200")
    nfk = pd.Series(buek.ravel()).map(units.nfkwe_mm).to_numpy("float32").reshape(h, w)
    sd_prof = pd.Series(buek.ravel()).map(units.sd_between_profiles_mm).to_numpy("float32").reshape(h, w)
    sig = np.sqrt(sd_prof ** 2 + NFK_LOOKUP_SIGMA_MM ** 2)
    lo, hi = np.maximum(nfk - Z90 * sig, 0), nfk + Z90 * sig
    conf = np.where(((lo < 90) & (hi > 90)) | ((lo < 140) & (hi > 140)), LOW, MEDIUM).astype("float32")
    conf[~np.isfinite(nfk)] = np.nan
    layers[("nfk", "derived")] = dict(value=nfk, lo=lo, hi=hi, conf=conf, kind="continuous", cmap="nfk",
                                      unit="mm", zone_m=20, native_m=None)

    pid = rasterize(((g, i + 1) for i, g in enumerate(parcels.geometry)), out_shape=(h, w), transform=transform,
                    fill=0, dtype="int32")
    numeric = {"clay": layers[("texture", "soilgrids")]["value"], "sand": layers["_sand"],
               "soc": layers[("soc", "soilgrids")]["value"], "twi": dem["twi"], "slope": dem["slope"],
               "rel_elev": dem["rel_elev"]}
    bzm = bodenzahl_model(numeric, buek, layers[("bodenzahl", "lbeg_bodenschaetzung")]["value"], pid, fall > 0)
    v = bzm["pred"]
    lo, hi = v - Z90 * bzm["rmse"], v + Z90 * bzm["rmse"]
    conf = np.where(((lo < 30) & (hi > 30)) | ((lo < 50) & (hi > 50)), LOW, MEDIUM).astype("float32")
    conf[~np.isfinite(v)] = np.nan
    layers[("bodenzahl", "derived")] = dict(value=v, lo=lo, hi=hi, conf=conf, kind="continuous", cmap="bodenzahl",
                                            unit="points", zone_m=20, native_m=None)
    meta = dict(nfk_units={int(u): dict(nfkwe_mm=round(r.nfkwe_mm, 1), sd_between_profiles_mm=round(r.sd_between_profiles_mm, 1),
                                        n_profiles=int(r.n_profiles), profiles=r.profiles)
                           for u, r in units.iterrows()},
                bodenzahl_model=dict(chosen=bzm["best"], scores=bzm["scores"], n_parcels=bzm["n_parcels"],
                                     n_px=bzm["n_px"], features=bzm["features"]))
    (RUN_DIR / "covariates" / "derived_soil.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    return meta


def build_yield(layers, fields_utm, dem, buek, transform, h, w):
    """Yield potential v1 (see poc/lib/yield_model.py). Adds the layer and returns model metadata."""
    shape = (h, w)
    seasons = ym.season_rel(fields_utm, SEG / "sentinel2", transform, shape)
    cwb = ym.cwb_apr_jun(SEG / "era5_history" / "daily.csv", SEG / "era5_history" / "cells.csv")
    scen = ym.scenarios(cwb)
    nd = ym.ndvi_component(seasons, cwb)
    yp_ndvi = {k: nanmedian3(nd.at(v)) for k, v in scen.items()}   # 3×3 median removes S2 striping

    fall, _ = ym.field_index(fields_utm, transform, shape)
    covs = {"clay": layers[("texture", "soilgrids")]["value"], "sand": layers["_sand"],
            "soc": layers[("soc", "soilgrids")]["value"], "nfk": layers[("nfk", "soilgrids")]["value"],
            "bodenzahl": layers[("bodenzahl", "lbeg_bodenschaetzung")]["value"],
            "twi": dem["twi"], "slope": dem["slope"], "rel_elev": dem["rel_elev"]}
    soil = ym.soil_model(covs, nd.level, fall, seasons.fid)
    yp, sigma, wgt = ym.blend(nd, yp_ndvi["normal"], soil, seasons.fid)

    unstable = np.nan_to_num(nd.sd_z) > 1.0
    conf = np.where(unstable | (wgt < 0.25), LOW, HIGH).astype("float32")   # refined per field (threshold 100)
    conf[~np.isfinite(yp)] = np.nan
    v = yp * 100
    layers[("yield_potential", "derived")] = dict(
        value=v, lo=v - Z90 * sigma * 100, hi=v + Z90 * sigma * 100, conf=conf, kind="continuous",
        cmap="yield_potential", unit="index", zone_m=10, native_m=10, nseas=nd.n, weight=wgt)
    write_cog(RUN_DIR / "covariates" / "yield_components.tif",
              np.round(np.stack([yp_ndvi["normal"], yp_ndvi["dry"], yp_ndvi["wet"], soil.pred, wgt, sigma,
                                 nd.slope * 100, buek]), 4), transform,
              ["ndvi_normal", "ndvi_dry", "ndvi_wet", "soil_model", "ndvi_weight", "sigma", "slope_per_100mm",
               "buek_unit"], dict(run_id=RUN_ID, note="relative to field mean = 1; not API layers"),
              overviews="NONE")
    meta = dict(model="yield_v1", scenario="normal", cwb_apr_jun_mm={str(k): round(v, 1) for k, v in cwb.loc[2019:].items()},
                scenarios_mm={k: round(v, 1) for k, v in scen.items()}, climate_years=list(ym.CLIMATE_YEARS),
                soil_model=dict(r2_oof=round(soil.r2_oof, 3), resid_sd=round(soil.resid_sd, 4),
                                n_train_px=soil.n_train, coef_per_sd=soil.coef))
    (RUN_DIR / "covariates" / "yield_model.json").write_text(json.dumps(meta, indent=1))
    return meta


# ---------------------------------------------------------------- per-field products

def zone_mask(g, buf_m, transform, shape_, centres, inside):
    z = g.buffer(-buf_m)
    if not z.is_empty:
        m = rasterize([z], out_shape=shape_, transform=transform, fill=0, dtype="uint8").astype(bool)
        if m.any():
            return m, f"inner_{buf_m}m"
    if centres.any():
        return centres, "full_field_fallback"
    return inside, "full_field_all_touched"


def png_grid(g4326):
    """EPSG:3857 grid for a field's PNG and its Leaflet bounds [[S,W],[N,E]]."""
    g = gpd.GeoSeries([g4326], crs="EPSG:4326").to_crs("EPSG:3857").iloc[0]
    lat = g4326.centroid.y
    res = PNG_GROUND_RES_M / math.cos(math.radians(lat))
    minx, miny, maxx, maxy = g.buffer(2 * res).bounds
    width, height = math.ceil((maxx - minx) / res), math.ceil((maxy - miny) / res)
    maxx, miny = minx + width * res, maxy - height * res
    t = from_origin(minx, maxy, res, res)
    corners = gpd.GeoSeries.from_xy([minx, maxx], [miny, maxy], crs="EPSG:3857").to_crs("EPSG:4326")
    bounds = [[round(corners.y[0], 7), round(corners.x[0], 7)], [round(corners.y[1], 7), round(corners.x[1], 7)]]
    mask = rasterize([g], out_shape=(height, width), transform=t, fill=0, dtype="uint8").astype(bool)
    return t, (height, width), mask, bounds


def to_png(arr, src_t, dst_t, dst_shape, mask, rgba_fn, path):
    dst = np.full(dst_shape, np.nan, "float32")
    reproject(arr.astype("float32"), dst, src_transform=src_t, src_crs=UTM, dst_transform=dst_t, dst_crs="EPSG:3857",
              resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
    dst[~mask] = np.nan
    Image.fromarray(rgba_fn(dst), "RGBA").save(path, optimize=True)


def field_level(conf_zone: np.ndarray) -> tuple[int, dict]:
    v = conf_zone[np.isfinite(conf_zone)]
    if v.size == 0:
        return LOW, {}
    shares = {LEVEL_NAME[k]: round(float((v == k).mean()), 3) for k in (LOW, MEDIUM, HIGH)}
    if shares["low"] > 0.5:
        return LOW, shares
    if shares["high"] >= 0.8:
        return HIGH, shares
    return MEDIUM, shares


def continuous_stats(v: np.ndarray) -> dict:
    return dict(mean=r(v.mean()), std=r(v.std()), min=r(v.min()), p10=r(np.percentile(v, 10)),
                p50=r(np.percentile(v, 50)), p90=r(np.percentile(v, 90)), max=r(v.max()))


def build_field(f, layers, transform, H, W, parcels, nibis_row, conn):
    pid = f.plotId
    g = f.geom_utm
    fw = from_bounds(*g.buffer(10).bounds, transform=transform)
    c0, r0 = math.floor(fw.col_off), math.floor(fw.row_off)
    c1, r1 = math.ceil(fw.col_off + fw.width), math.ceil(fw.row_off + fw.height)
    win = Window(c0, r0, c1 - c0, r1 - r0).intersection(Window(0, 0, W, H))
    wt = rasterio.windows.transform(win, transform)
    shp = (int(win.height), int(win.width))
    sl = (slice(int(win.row_off), int(win.row_off + win.height)), slice(int(win.col_off), int(win.col_off + win.width)))
    inside = rasterize([g], out_shape=shp, transform=wt, fill=0, dtype="uint8", all_touched=True).astype(bool)
    centres = rasterize([g], out_shape=shp, transform=wt, fill=0, dtype="uint8").astype(bool)
    inner10 = rasterize([g.buffer(-10)], out_shape=shp, transform=wt, fill=0, dtype="uint8").astype(bool) if not g.buffer(-10).is_empty else np.zeros(shp, bool)
    pt, pshape, pmask, bounds = png_grid(f.geometry)
    fdir = RUN_DIR / "fields" / pid
    fdir.mkdir(parents=True, exist_ok=True)
    in_ni = (nibis_row.get("L849_area_share") or 0) > 0 or (nibis_row.get("L816_area_share") or 0) > 0
    small = f.area_geom_ha < 6.25  # smaller than one 250 m SoilGrids cell
    rows = []

    for key, L in layers.items():
        if not isinstance(key, tuple):
            continue
        param, source = key
        rel =f"runs/{RUN_ID}/fields/{pid}/{param}__{source}"
        row = dict(run_id=RUN_ID, plot_id=pid, parameter=param, source=source, unit=COLORMAPS[L["cmap"]]["unit"],
                   colormap_id=L["cmap"], status=None, reason=None, coverage=0.0, stats_zone=None,
                   stats_json=None, confidence_json=None, geotiff_path=None, png_path=None, conf_png_path=None,
                   provenance_json=json.dumps({"native_resolution_m": L["native_m"], "grid": "EPSG:32632 10 m"}))
        if param == "yield_potential":
            row["provenance_json"] = json.dumps({"native_resolution_m": 10, "grid": "EPSG:32632 10 m",
                                                 **{k: YIELD_META[k] for k in ("model", "scenario", "scenarios_mm")}})
        val, lo, hi, conf = (L[k][sl].copy() for k in ("value", "lo", "hi", "conf"))
        zone, zone_name = zone_mask(g, L["zone_m"], wt, shp, centres, inside)
        drivers = []

        if source == "lbeg_bodenschaetzung":
            if not in_ni:
                row.update(status="unavailable", reason="outside_source_region:niedersachsen")
                rows.append(row)
                continue
            cov = float(parcels.intersection(g).area.sum() / g.area) if len(parcels) else 0.0
            row["coverage"] = round(min(cov, 1.0), 3)
        else:
            # NDVI-based values exist only in the inner zone (edge pixels mix crop and hedges), so
            # coverage is measured there; the excluded edge strip is reported as a driver instead.
            valid = np.isfinite(val) & inside
            row["coverage"] = round(float(valid.sum() / max(inside.sum(), 1)), 3)

        if param == "yield_potential":
            zv_ = zone & np.isfinite(val)
            zmean = np.nanmean(val[zv_]) if zv_.any() else np.nanmean(val[inside]) if (inside & np.isfinite(val)).any() else np.nan
            if not np.isfinite(zmean):
                row.update(status="unavailable", reason="no_data_in_source")
                rows.append(row)
                continue
            scale = 100 / zmean
            val, lo, hi = val * scale, lo * scale, hi * scale
            # threshold = field mean: can we tell above vs below average?
            conf = np.where(conf == LOW, LOW, np.where((lo < 100) & (hi > 100), MEDIUM, HIGH)).astype("float32")
            edge = inside & ~inner10
            conf[edge & np.isfinite(conf)] = np.maximum(conf[edge & np.isfinite(conf)] - 1, LOW)
            conf[~np.isfinite(val)] = np.nan
            wz = L["weight"][sl][inside]
            drivers += ["ndvi_proxy_not_yield", "no_harvest_data_for_validation"]
            if (wz > 0).sum() == 0:
                drivers += ["soil_model_only", "no_ndvi_history"]
            else:
                drivers.append("edge_strip_soil_model_weighted")
                if np.nanmedian(L["nseas"][sl][zone & (L["weight"][sl] > 0)]) < 6:
                    drivers.append("few_ndvi_seasons")

        if row["coverage"] == 0 or not (inside & np.isfinite(val)).any():
            row.update(status="unavailable", reason="no_parcel_downloaded_for_field"
                       if source == "lbeg_bodenschaetzung" else "no_data_in_source")
            rows.append(row)
            continue
        row["status"] = "ok" if row["coverage"] >= 0.95 else "partial"
        if row["status"] == "partial":
            row["reason"] = "only_parcels_at_sample_point_downloaded" if source == "lbeg_bodenschaetzung" else "partial_source_coverage"

        for a in (val, lo, hi, conf):
            a[~inside] = np.nan
        zv = zone & np.isfinite(val)
        if not zv.any():
            zv = inside & np.isfinite(val)
            zone_name = "full_field_all_touched"
        row["stats_zone"] = zone_name
        if L["kind"] == "categorical":
            codes, counts = np.unique(val[zv], return_counts=True)
            classes = {BODENART_CODES[int(c) - 1]: round(float(n / counts.sum()), 3) for c, n in zip(codes, counts)}
            stats = dict(classes=classes, dominant=max(classes, key=classes.get), n_px=int(zv.sum()))
            if source == "lbeg_bodenschaetzung":
                stats["klassenzeichen"] = sorted(parcels[parcels.intersects(g)].klassenzeichen.dropna().unique().tolist())
        else:
            stats = continuous_stats(val[zv]) | dict(n_px=int(zv.sum()))
            if (param, source) == ("texture", "soilgrids"):
                sand, silt = layers["_sand"][sl][zv].mean(), layers["_silt"][sl][zv].mean()
                stats |= dict(clay_mean=stats["mean"], sand_mean=r(sand), silt_mean=r(silt),
                              usda_class=usda_class(sand, silt, stats["mean"]))
        stats["zone"] = zone_name
        row["stats_json"] = json.dumps(stats)

        level, shares = field_level(conf[zv])
        if source == "soilgrids":
            drivers.append("single_coarse_source")
            if small:
                drivers.append("pixel_larger_than_field")
                level = LOW
            if L.get("calibrated"):
                drivers.append("error_calibrated_west")
            if shares.get("low", 0) > 0.5:
                drivers.append({"ph": "range_crosses_threshold:liming_ph_5.5", "nfk": "range_crosses_threshold:nfk_90_140_mm",
                                "texture": "range_wider_than_texture_class", "soc": "range_wider_than_half_value"}[param])
        if source == "derived" and param == "nfk":
            drivers += ["buek200_1to200000_nearest_point", "lookup_table_approximate"]
            if shares.get("low", 0) > 0.5:
                drivers.append("range_crosses_threshold:nfk_90_140_mm")
        if source == "derived" and param == "bodenzahl":
            n_par = DERIVED_META["bodenzahl_model"]["n_parcels"]
            drivers.append(f"model_trained_on_{n_par}_parcels")
            if not in_ni:
                drivers.append("extrapolated_across_state_border")
            if shares.get("low", 0) > 0.5:
                drivers.append("range_crosses_threshold:bodenzahl_30_50")
        if source == "lbeg_bodenschaetzung":
            drivers.append("official_survey_1to5000")
            if param == "bodenzahl":
                drivers.append("interval_assumed_not_calibrated")
        if row["status"] == "partial":
            drivers.append("partial_coverage")
            level = max(LOW, level - 1)
        if zone_name != f"inner_{L['zone_m']}m":
            drivers.append("no_inner_zone_edge_pixels_only")
            level = max(LOW, level - 1)
        if param == "yield_potential":
            if shares.get("low", 0) > 0.25:
                drivers.append("unstable_or_edge_pixels")
            if "soil_model_only" in drivers:
                level = LOW
        interval = [r(np.nanmean(lo[zv])), r(np.nanmean(hi[zv]))] if L["kind"] == "continuous" else None
        row["confidence_json"] = json.dumps(dict(level=LEVEL_NAME[level], interval_90=interval, drivers=drivers,
                                                 pixel_shares=shares))

        write_cog(fdir / f"{param}__{source}.tif", np.stack([val, lo, hi, conf]), wt,
                  ["value", "lo90", "hi90", "confidence"],
                  dict(parameter=param, source=source, unit=row["unit"], run_id=RUN_ID, plot_id=pid,
                       confidence_codes="1=low 2=medium 3=high"))
        to_png(val, wt, pt, pshape, pmask, lambda a: colorize(a, COLORMAPS[L["cmap"]]), fdir / f"{param}__{source}.png")
        to_png(conf, wt, pt, pshape, pmask, hatch, fdir / f"{param}__{source}__conf.png")
        row.update(geotiff_path=rel + ".tif", png_path=rel + ".png", conf_png_path=rel + "__conf.png")
        rows.append(row)

    # BK50 nFKWe: in the source, not in what we downloaded
    rows.append(dict(run_id=RUN_ID, plot_id=pid, parameter="nfk", source="lbeg_bk50", unit="mm", colormap_id="nfk",
                     status="unavailable", coverage=0.0,
                     reason="attribute_not_in_downloaded_data" if in_ni else "outside_source_region:niedersachsen",
                     stats_zone=None, stats_json=None, confidence_json=None, geotiff_path=None, png_path=None,
                     conf_png_path=None, provenance_json=None))
    cols = list(rows[0])
    conn.executemany(f"INSERT INTO field_layers ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                     [tuple(x[c] for c in cols) for x in rows])
    return bounds, in_ni


# ---------------------------------------------------------------- samples

def assemble_response(conn, fc: dict, parameters: list[str], sources: list[str]) -> dict:
    """Reference implementation of the response for features matched by plotId (or outside the farm)."""
    conn.row_factory = sqlite3.Row
    run = conn.execute("SELECT * FROM runs WHERE is_current = 1").fetchone()
    provided = {(x["source"], x["parameter"]) for x in conn.execute("SELECT source, parameter FROM source_parameters")}
    cmaps = {x["colormap_id"]: json.loads(x["json"]) for x in conn.execute("SELECT * FROM colormaps")}
    out = []
    for feat in fc["features"]:
        pid = (feat.get("properties") or {}).get("plotId")
        frow = conn.execute("SELECT * FROM fields WHERE plot_id = ?", (pid,)).fetchone() if pid else None
        entry = {"id": feat.get("id"), "matched_plot_id": frow["plot_id"] if frow else None,
                 "match": "plot_id" if frow else "outside_coverage_area",
                 "field_name": frow["field_name"] if frow else None,
                 "bounds": json.loads(frow["bounds_json"]) if frow else None, "layers": []}
        for p in parameters:
            for s in sources:
                base = {"parameter": p, "source": s}
                if (s, p) not in provided:
                    entry["layers"].append(base | {"status": "not_applicable", "reason": "source_does_not_provide_parameter"})
                    continue
                if not frow:
                    entry["layers"].append(base | {"status": "unavailable", "reason": "outside_coverage_area"})
                    continue
                fl = conn.execute("SELECT * FROM field_layers WHERE run_id=? AND plot_id=? AND parameter=? AND source=?",
                                  (run["run_id"], pid, p, s)).fetchone()
                lay = base | {"status": fl["status"], "reason": fl["reason"], "coverage": fl["coverage"], "unit": fl["unit"]}
                if fl["status"] in ("ok", "partial"):
                    conf = json.loads(fl["confidence_json"])
                    conf |= {"raster_url": f"/static/{fl['geotiff_path']}#band=4", "png_url": f"/static/{fl['conf_png_path']}"}
                    lay |= {"png_url": f"/static/{fl['png_path']}", "geotiff_url": f"/static/{fl['geotiff_path']}",
                            "stats": json.loads(fl["stats_json"]), "colormap": cmaps[fl["colormap_id"]],
                            "confidence": conf, "provenance": json.loads(fl["provenance_json"])}
                entry["layers"].append(lay)
        out.append(entry)
    return {"run_id": run["run_id"], "data_as_of": json.loads(run["data_as_of_json"]), "fields": out}


# ---------------------------------------------------------------- main

def main():
    if STORE.exists():
        shutil.rmtree(STORE)
    (RUN_DIR / "regional").mkdir(parents=True)
    (RUN_DIR / "covariates").mkdir(parents=True)
    transform, H, W = load_grid()

    fields = gpd.read_file(SEG / "clean" / "fields_clean.geojson").to_crs("EPSG:4326")
    fields["geom_utm"] = fields.to_crs(UTM).geometry
    nibis = pd.read_csv(SEG / "nibis" / "nibis_fields.csv").set_index("plotId")
    parcels = load_bodenschaetzung()
    print(f"{len(fields)} fields, {len(parcels)} Bodenschätzung parcels")

    layers = build_regional(transform, H, W, parcels)
    # bare-ground pixels: field interiors (10 m in from the edge, away from hedges and tree lines)
    ground = rasterize(fields.to_crs(UTM).buffer(-10).loc[lambda g: ~g.is_empty], out_shape=(H, W),
                       transform=transform, fill=0, dtype="uint8").astype(bool)
    dem = terrain(SEG / "raw" / "dem" / "farm_window.tif", transform, H, W, UTM, ground)
    cal = apply_texture_calibration(layers, parcels, transform, H, W)
    print("texture calibration:", {k: v for k, v in cal.items() if k != "by_class"})
    buek = buek_unit_raster(SEG / "buek200_points.csv", transform, H, W, UTM)
    fall, _ = ym.field_index(fields.to_crs(UTM), transform, (H, W))
    global DERIVED_META, YIELD_META
    DERIVED_META = build_derived_soil(layers, dem, buek, parcels, fall, transform, H, W)
    print("bodenzahl model:", DERIVED_META["bodenzahl_model"]["chosen"], DERIVED_META["bodenzahl_model"]["scores"])
    YIELD_META = build_yield(layers, fields.to_crs(UTM), dem, buek, transform, H, W)
    print("yield model:", YIELD_META["soil_model"], YIELD_META["scenarios_mm"])
    write_cog(RUN_DIR / "covariates" / "dem__copernicus.tif", np.round(np.stack(list(dem.values())), 2), transform, list(dem),
              dict(source="Copernicus DEM GLO-30 surface model; ground = field interiors, rest interpolated; smoothed ~50 m", run_id=RUN_ID,
                   units="elev m, slope deg, twi ln(m), rel_elev m vs 210 m box mean, ground_mask 1 = measured ground"), overviews="NONE")
    regional_rows = []
    for key, L in layers.items():
        if not isinstance(key, tuple):
            continue
        param, source = key
        p = RUN_DIR / "regional" / f"{param}__{source}.tif"
        write_cog(p, np.stack([L["value"], L["lo"], L["hi"], L["conf"]]), transform,
                  ["value", "lo90", "hi90", "confidence"],
                  dict(parameter=param, source=source, run_id=RUN_ID, confidence_codes="1=low 2=medium 3=high",
                       note="yield_potential: divide by the field's inner-10 m mean and ×100 to get the field index"
                       if param == "yield_potential" else ""))
        regional_rows.append((RUN_ID, param, source, str(p.relative_to(STORE)), L["kind"], COLORMAPS[L["cmap"]]["unit"], L["cmap"]))
    parcels.to_crs("EPSG:4326").to_file(RUN_DIR / "regional" / "bodenschaetzung_parcels.geojson", driver="GeoJSON")

    db = STORE / "soil.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript((POC / "schema.sql").read_text())
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    as_of = {"sentinel2": "2026-10-03", "weather": "2026-09-27", "soilgrids": "v2.0 (pulled 2026-10-03)",
             "nibis": "pulled 2026-10-03"}
    conn.execute("INSERT INTO runs VALUES (?,?,?,?,?)", (RUN_ID, now, 1, json.dumps(as_of),
                 "POC: built from data already on disk, no refresh"))
    conn.executemany("INSERT INTO sources VALUES (?,?,?,?,?,?,?)", SOURCES)
    conn.executemany("INSERT INTO parameters VALUES (?,?,?)", PARAMETERS)
    conn.executemany("INSERT INTO source_parameters VALUES (?,?,?)", SOURCE_PARAMETERS)
    conn.executemany("INSERT INTO colormaps VALUES (?,?)", [(k, json.dumps(v)) for k, v in COLORMAPS.items()])
    conn.executemany("INSERT INTO regional_rasters VALUES (?,?,?,?,?,?,?)", regional_rows)
    west_, south, east_, north = rasterio.transform.array_bounds(H, W, transform)
    extent = gpd.GeoSeries([box(west_, south, east_, north)], crs=UTM).to_crs("EPSG:4326").iloc[0]
    conn.execute("INSERT INTO coverage_areas VALUES (?,?,?)", ("farm_raster_extent", json.dumps(mapping(extent)),
                 "Polygons fully inside can be clipped from regional rasters; outside → unavailable"))

    for f in fields.itertuples():
        nrow = nibis.loc[f.plotId].to_dict() if f.plotId in nibis.index else {}
        bounds, in_ni = build_field(f, layers, transform, H, W, parcels, nrow, conn)
        conn.execute("INSERT INTO fields VALUES (?,?,?,?,?,?,?,?,?,?)", (
            f.plotId, f.fieldName, round(f.area_geom_ha, 4), int(bool(f.use_for_stats)), "NI" if in_ni else "ST",
            geom_hash(f.geometry), json.dumps(mapping(f.geometry)), json.dumps(bounds),
            f.inner20m_area_ha, f.flags or None))
    conn.commit()

    # samples: one west field (best Bodenschätzung coverage), one large east field, one sliver, one outside polygon
    q = conn.execute("""SELECT f.plot_id FROM fields f JOIN field_layers l ON l.plot_id=f.plot_id
                        WHERE l.parameter='bodenzahl' AND l.source='lbeg_bodenschaetzung' AND l.status IN ('ok','partial') ORDER BY l.coverage DESC, f.area_ha DESC LIMIT 1""")
    west = q.fetchone()[0]
    east = conn.execute("SELECT plot_id FROM fields WHERE state='ST' AND use_for_stats=1 ORDER BY area_ha DESC LIMIT 1").fetchone()[0]
    sliver = conn.execute("SELECT plot_id FROM fields WHERE use_for_stats=0 ORDER BY area_ha LIMIT 1").fetchone()[0]
    feats = []
    for i, pid in enumerate([west, east, sliver], 1):
        g = fields.set_index("plotId").loc[pid]
        feats.append({"type": "Feature", "id": f"f{i}", "properties": {"plotId": pid, "fieldName": g.fieldName},
                      "geometry": mapping(g.geometry)})
    feats.append({"type": "Feature", "id": "f4", "properties": {"note": "Hildesheim, outside the farm"},
                  "geometry": mapping(box(9.95, 52.22, 9.952, 52.221))})
    req = {"type": "FeatureCollection", "features": feats,
           "parameters": [p[0] for p in PARAMETERS],
           "sources": [s[0] for s in SOURCES]}
    (POC / "samples").mkdir(exist_ok=True)
    (POC / "samples" / "request.json").write_text(json.dumps(req, indent=1, ensure_ascii=False))
    resp = assemble_response(conn, req, req["parameters"], req["sources"])
    (POC / "samples" / "response.json").write_text(json.dumps(resp, indent=1, ensure_ascii=False))
    conn.close()

    n = sum(1 for _ in STORE.rglob("*") if _.is_file())
    mb = sum(p.stat().st_size for p in STORE.rglob("*") if p.is_file()) / 1e6
    print(f"store: {n} files, {mb:.1f} MB; samples: west={west} east={east} sliver={sliver}")


if __name__ == "__main__":
    main()
