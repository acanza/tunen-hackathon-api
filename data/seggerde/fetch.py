# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pandas", "numpy", "geopandas", "shapely", "pyproj", "rasterio", "exactextract"]
# ///
"""Pull every EDA source for the LuF Seggerde farm fields and compute per-field coverage.

Run from this folder:  uv run fetch.py            (cached raw files are reused)
                       uv run fetch.py --force    (re-download everything)

Stages (each saves untouched responses under raw/):
  fields     active fields only (archived ones are near-copies), repaired geometry
  soilgrids  WCS GeoTIFF per property/depth/stat in native Homolosine 250 m grid
  nibis      BK50 (L816) + Bodenschaetzung (L849) GetFeatureInfo at one point per field
  buek200    legend-unit polygons intersecting the farm (ArcGIS REST), area share per field
  dem        Copernicus GLO-30 window over the farm, slope, zonal stats with/without inner buffer
  openmeteo  ERA5 archive (last 30 days) + ICON forecast at one point per field
"""
import json, sys, time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from exactextract import exact_extract
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.windows import from_bounds

HERE = Path(__file__).parent
RAW = HERE / "raw"
FIELDS_SRC = HERE.parent.parent / "LuF-Seggerde-Dev-fields.geojson"
FORCE = "--force" in sys.argv
UA = {"User-Agent": "tunen-hackathon-eda/0.1"}
WORK_CRS = "EPSG:25832"
IGH = CRS.from_proj4("+proj=igh +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs")
INNER_BUFFER_M = -20  # drop field edges (hedges, roads, tree lines) before statistics


def get(url, params=None, timeout=60, tries=4, method="GET", **kw):
    for i in range(tries):
        try:
            r = requests.request(method, url, params=params, timeout=timeout, headers=UA, **kw)
            if r.status_code == 200:
                return r
            print("  http", r.status_code, url[:80], flush=True)
        except requests.RequestException as e:
            print("  err", e.__class__.__name__, url[:80], flush=True)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"gave up: {url}")


def cached(path: Path, fetch):
    """Return bytes from path, fetching (and saving) them first if missing."""
    if FORCE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch())
    return path.read_bytes()


def multipoly(geoms):
    """Polygonal parts only, as MultiPolygon (exactextract rejects mixed types); empty -> None."""
    from shapely.geometry import MultiPolygon, Polygon
    out = []
    for g in geoms:
        parts = [] if g is None or g.is_empty else \
            [p for p in getattr(g, "geoms", [g]) if isinstance(p, (Polygon, MultiPolygon))]
        polys = [q for p in parts for q in getattr(p, "geoms", [p])]
        out.append(MultiPolygon(polys) if polys else None)
    return out


def zonal(raster, geoms, ops, crs):
    """exact_extract over non-empty geometries; rows for empty geometries come back as NaN."""
    mp = multipoly(geoms)
    ok = [i for i, g in enumerate(mp) if g is not None]
    gdf = gpd.GeoDataFrame(geometry=[mp[i] for i in ok], crs=crs)
    ex = exact_extract(str(raster), gdf, ops, output="pandas")
    ex.index = ok
    return ex.reindex(range(len(mp)))


# ---------------------------------------------------------------- fields
def load_fields():
    g = gpd.read_file(FIELDS_SRC)
    g["geom_was_invalid"] = ~g.is_valid
    g["geometry"] = g.geometry.make_valid()
    act = g[~g.isArchived].copy().reset_index(drop=True)
    u = act.to_crs(WORK_CRS)
    act["area_calc_ha"] = u.area / 1e4
    inner = u.buffer(INNER_BUFFER_M)
    act["inner_area_ha"] = inner.area / 1e4
    rp = u.representative_point().to_crs(4326)  # guaranteed inside the polygon (centroid is not)
    act["pt_lon"], act["pt_lat"] = rp.x.round(6), rp.y.round(6)
    act.to_file(HERE / "fields_active.geojson", driver="GeoJSON")
    return act


# ---------------------------------------------------------------- soilgrids (WCS)
SG_PROPS = ["clay", "sand", "silt", "phh2o", "soc", "nitrogen", "cec", "bdod", "cfvo", "wv0033", "wv1500"]
SG_DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]
SG_STATS = ["Q0.05", "Q0.5", "Q0.95", "mean"]
SG_DFACTOR = {"bdod": 100, "nitrogen": 100}  # all others: 10


def soilgrids(fields):
    to_igh = Transformer.from_crs("EPSG:4326", IGH, always_xy=True)
    w, s, e, n = fields.total_bounds
    pad = 0.01
    xs, ys = zip(*[to_igh.transform(x, y) for x in (w - pad, e + pad) for y in (s - pad, n + pad)])
    box = (min(xs), max(xs), min(ys), max(ys))
    f_igh = fields.to_crs(IGH)
    f_igh_inner = fields.to_crs(WORK_CRS).buffer(INNER_BUFFER_M).to_crs(IGH)
    jobs = [(p, d, st) for p in SG_PROPS for d in SG_DEPTHS for st in SG_STATS] + [("ocs", "0-30cm", st) for st in SG_STATS]
    rows, timing = [], []
    for prop, depth, stat in jobs:
        cov = f"{prop}_{depth}_{stat}"
        path = RAW / "soilgrids" / f"{cov}.tif"
        t0 = time.time()
        cached(path, lambda: get(
            f"https://maps.isric.org/mapserv?map=/map/{prop}.map",
            params=[("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"),
                    ("COVERAGEID", cov), ("FORMAT", "image/tiff"),
                    ("SUBSET", f"X({box[0]},{box[1]})"), ("SUBSET", f"Y({box[2]},{box[3]})")],
            timeout=120).content)
        timing.append(time.time() - t0)
        with rasterio.open(path) as src:
            a = src.read(1).astype("float64")
            # GeoTIFF carries no CRS and no nodata; 0 marks "no prediction" (urban, water, gaps)
            a[a == 0] = np.nan
            profile = dict(driver="GTiff", height=a.shape[0], width=a.shape[1], count=1,
                           dtype="float64", crs=IGH, transform=src.transform, nodata=np.nan)
        fixed = RAW / "soilgrids_fixed" / f"{cov}.tif"
        fixed.parent.mkdir(exist_ok=True)
        with rasterio.open(fixed, "w", **profile) as dst:
            dst.write(a, 1)
        div = SG_DFACTOR.get(prop, 10)
        for label, geoms in (("full", f_igh.geometry), ("inner20m", f_igh_inner)):
            # exactextract: coverage-fraction weighted stats; 'count' = sum of covered pixel fractions
            ex = zonal(fixed, geoms, ["mean", "min", "max", "count"], IGH)
            for i, r in ex.iterrows():
                v = pd.to_numeric(r[["mean", "min", "max"]], errors="coerce") / div  # None -> NaN
                rows.append(dict(plotId=fields.plotId[i], prop=prop, depth=depth, stat=stat, zone=label,
                                 mean=v["mean"], min=v["min"], max=v["max"], valid_pixel_equiv=r["count"]))
        # pixels touched incl. nodata, for the missing-value share
        if stat == "Q0.5" and depth == "0-5cm":
            ones = profile | {"dtype": "uint8", "nodata": None}
            tmp = RAW / "soilgrids_fixed" / "_ones.tif"
            with rasterio.open(tmp, "w", **ones) as dst:
                dst.write(np.ones(a.shape, "uint8"), 1)
            tot = zonal(tmp, f_igh.geometry, ["count"], IGH)["count"]
            for i, c in enumerate(tot):
                rows.append(dict(plotId=fields.plotId[i], prop=prop, depth="_all", stat="_total_pixel_equiv",
                                 zone="full", valid_pixel_equiv=c))
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "soilgrids_fields.csv", index=False)
    print(f"soilgrids: {len(jobs)} coverages, median {np.median(timing):.2f}s each (0 = cached)")
    return df


# ---------------------------------------------------------------- nibis
NIBIS = "https://nibis.lbeg.de/net3/public/ogc.ashx?PkgId=24"


def nibis(fields):
    tr = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)
    rows = []
    for _, f in fields.iterrows():
        x, y = tr.transform(f.pt_lon, f.pt_lat)
        for layer in ("L816", "L849"):
            path = RAW / "nibis" / f"{layer}_{f.plotId}.json"
            body = cached(path, lambda: get(NIBIS, params=dict(
                SERVICE="WMS", VERSION="1.3.0", REQUEST="GetFeatureInfo", LAYERS=layer, QUERY_LAYERS=layer,
                STYLES="", CRS="EPSG:25832", BBOX=f"{x-5:.2f},{y-5:.2f},{x+5:.2f},{y+5:.2f}",
                WIDTH=101, HEIGHT=101, I=50, J=50, INFO_FORMAT="application/geo+json", FEATURE_COUNT=5),
                timeout=8).content)
            try:
                feats = json.loads(body).get("features", [])
            except json.JSONDecodeError:
                feats = None
            rows.append(dict(plotId=f.plotId, layer=layer, n_features=None if feats is None else len(feats),
                             props=json.dumps(feats[0]["properties"], ensure_ascii=False) if feats else None))
            time.sleep(0.1)
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "nibis_fields.csv", index=False)
    print("nibis: features per layer", df.groupby("layer").n_features.apply(lambda s: (s > 0).sum()).to_dict())
    return df


# ---------------------------------------------------------------- buek200
BUEK = "https://services.bgr.de/arcgis/rest/services/boden/buek200/MapServer"


def buek200(fields, step_m=125):
    """The service returns unit attributes but withholds polygon geometry (geometry: null in every
    format), so area shares are estimated from point queries on a step_m grid inside each field."""
    w, s, e, n = fields.total_bounds
    env = dict(geometry=f"{w},{s},{e},{n}", geometryType="esriGeometryEnvelope", inSR=4326,
               spatialRel="esriSpatialRelIntersects", outFields="*", returnGeometry="false", f="json")
    sheets = json.loads(cached(RAW / "buek200" / "L0_sheets.json", lambda: get(f"{BUEK}/0/query", params=env).content))
    layers = json.loads(cached(RAW / "buek200" / "service.json", lambda: get(BUEK, params={"f": "json"}).content))["layers"]
    sheet_ids = []
    for feat in sheets["features"]:
        key = feat["attributes"]["BLATTNUM"].replace(" ", "")
        lyr = next(l for l in layers if l["name"].replace(" ", "").startswith(key))
        sheet_ids.append(lyr["id"])
        print(f"buek200: sheet {key} -> layer {lyr['id']} {lyr['name']}")
        cached(RAW / "buek200" / f"L{lyr['id']}_units_on_farm.json",
               lambda: get(f"{BUEK}/{lyr['id']}/query", params=env).content)
    assert len(sheet_ids) == 1, "farm spans several map sheets; query each point against all of them"
    lid = sheet_ids[0]
    u = fields.to_crs(WORK_CRS)
    to4326 = Transformer.from_crs(WORK_CRS, "EPSG:4326", always_xy=True)
    rows = []
    for i, f in u.iterrows():
        x0, y0, x1, y1 = f.geometry.bounds
        gx, gy = np.meshgrid(np.arange(x0 + step_m / 2, x1, step_m), np.arange(y0 + step_m / 2, y1, step_m))
        pts = [(x, y) for x, y in zip(gx.ravel(), gy.ravel()) if f.geometry.contains(gpd.points_from_xy([x], [y])[0])]
        if not pts:  # small field: fall back to its representative point
            p = f.geometry.representative_point(); pts = [(p.x, p.y)]
        for x, y in pts:
            lon, lat = to4326.transform(x, y)
            path = RAW / "buek200" / "points" / f"{lon:.5f}_{lat:.5f}.json"
            body = cached(path, lambda: get(f"{BUEK}/{lid}/query", params=dict(
                geometry=f"{lon},{lat}", geometryType="esriGeometryPoint", inSR=4326,
                spatialRel="esriSpatialRelIntersects", outFields="TKLE_NR,Legende,LEG_TEXT",
                returnGeometry="false", f="json")).content)
            feats = json.loads(body).get("features", [])
            a = feats[0]["attributes"] if feats else {}
            rows.append(dict(plotId=fields.plotId[i], lon=lon, lat=lat, n_pts=len(pts), **a))
    pts = pd.DataFrame(rows)
    pts.to_csv(HERE / "buek200_points.csv", index=False)
    share = (pts.groupby(["plotId", "TKLE_NR", "Legende"], dropna=False).size()
             / pts.groupby("plotId").size()).rename("share").reset_index()
    share.to_csv(HERE / "buek200_fields.csv", index=False)
    print(f"buek200: {len(pts)} points, {pts.TKLE_NR.nunique()} units on farm, "
          f"{(pts.TKLE_NR.isna()).sum()} points without a unit")
    for tk in pts["TKLE_NR"].dropna().unique():
        cached(RAW / "buek200" / f"profile_{int(tk)}.html",
               lambda: get("https://fisbo.bgr.de/app/FISBoBGR_Profilanzeige/getProfile.php",
                           params={"KARTE": "BUEK200", "LEGNR": int(tk)}).content)
    return share


# ---------------------------------------------------------------- dem
def dem(fields):
    w, s, e, n = fields.total_bounds
    pad = 0.005
    tiles = {(int(np.floor(la)), int(np.floor(lo))) for lo in (w - pad, e + pad) for la in (s - pad, n + pad)}
    assert len(tiles) == 1, f"farm spans several DEM tiles {tiles}; merge needed"
    la, lo = tiles.pop()
    name = f"Copernicus_DSM_COG_10_N{la:02d}_00_E{lo:03d}_00_DEM"
    url = f"https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif"
    out = RAW / "dem" / "farm_window.tif"
    if FORCE or not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"), rasterio.open(url) as src:
            win = from_bounds(w - pad, s - pad, e + pad, n + pad, src.transform).round_offsets().round_lengths()
            a = src.read(1, window=win)
            prof = src.profile | dict(height=a.shape[0], width=a.shape[1], transform=src.window_transform(win),
                                      driver="GTiff", tiled=False, compress="deflate")
            prof.pop("blockxsize", None); prof.pop("blockysize", None)
        with rasterio.open(out, "w", **prof) as dst:
            dst.write(a, 1)
    with rasterio.open(out) as src:
        z = src.read(1).astype("float64")
        T = src.transform
        lat_c = (s + n) / 2
        dx = abs(T.a) * 111320 * np.cos(np.radians(lat_c))
        dy = abs(T.e) * 110574
        zp = np.pad(z, 1, mode="edge")
        # Horn 3x3
        dzdx = ((zp[:-2, 2:] + 2 * zp[1:-1, 2:] + zp[2:, 2:]) - (zp[:-2, :-2] + 2 * zp[1:-1, :-2] + zp[2:, :-2])) / (8 * dx)
        dzdy = ((zp[2:, :-2] + 2 * zp[2:, 1:-1] + zp[2:, 2:]) - (zp[:-2, :-2] + 2 * zp[:-2, 1:-1] + zp[:-2, 2:])) / (8 * dy)
        slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
        prof = src.profile | dict(dtype="float64")
    sl = RAW / "dem" / "farm_slope_deg.tif"
    with rasterio.open(sl, "w", **prof) as dst:
        dst.write(slope, 1)
    f4326 = fields.geometry
    inner = fields.to_crs(WORK_CRS).buffer(INNER_BUFFER_M).to_crs(4326)
    rows = []
    for zone, geoms in (("full", f4326), ("inner20m", inner)):
        ez = zonal(out, geoms, ["mean", "min", "max", "count"], 4326)
        es = zonal(sl, geoms, ["mean", "max", "quantile(q=0.9)"], 4326)
        for i in range(len(fields)):
            rows.append(dict(plotId=fields.plotId[i], zone=zone, elev_mean=ez["mean"][i], elev_min=ez["min"][i],
                             elev_max=ez["max"][i], dem_pixel_equiv=ez["count"][i], slope_mean=es["mean"][i],
                             slope_p90=es.iloc[i, 2], slope_max=es["max"][i]))
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "dem_fields.csv", index=False)
    print(f"dem: tile {name}, window {z.shape}, pixel {dx:.1f} x {dy:.1f} m")
    return df


# ---------------------------------------------------------------- open-meteo
def openmeteo(fields):
    lats = ",".join(map(str, fields.pt_lat)); lons = ",".join(map(str, fields.pt_lon))
    today = pd.Timestamp("today").normalize()
    start, end = (today - pd.Timedelta(days=30)).date(), (today - pd.Timedelta(days=1)).date()
    soil = ",".join(f"soil_moisture_{d}" for d in ("0_to_7cm", "7_to_28cm", "28_to_100cm", "100_to_255cm"))
    arch = json.loads(cached(RAW / "openmeteo" / f"archive_{start}_{end}.json", lambda: get(
        "https://archive-api.open-meteo.com/v1/archive", timeout=120, params=dict(
            latitude=lats, longitude=lons, start_date=start, end_date=end, hourly=soil,
            daily="precipitation_sum,et0_fao_evapotranspiration", models="era5_seamless", timezone="UTC")).content))
    fc = json.loads(cached(RAW / "openmeteo" / f"forecast_{today.date()}.json", lambda: get(
        "https://api.open-meteo.com/v1/forecast", timeout=120, params=dict(
            latitude=lats, longitude=lons, forecast_days=7, models="icon_seamless", timezone="UTC",
            hourly="soil_moisture_0_to_1cm,soil_moisture_9_to_27cm,soil_temperature_6cm")).content))
    arch = arch if isinstance(arch, list) else [arch]
    fc = fc if isinstance(fc, list) else [fc]
    rows = []
    for i, (a, f) in enumerate(zip(arch, fc)):
        h = pd.DataFrame(a["hourly"]); d = pd.DataFrame(a["daily"])
        sm = h["soil_moisture_0_to_7cm"]
        last_valid = h.time[sm.notna()].max() if sm.notna().any() else None
        rows.append(dict(plotId=fields.plotId[i], era5_cell_lat=a["latitude"], era5_cell_lon=a["longitude"],
                         icon_cell_lat=f["latitude"], icon_cell_lon=f["longitude"],
                         sm0_7_null_share=sm.isna().mean(), sm0_7_last_valid=last_valid,
                         sm0_7_mean=sm.mean(), precip_30d_mm=d.precipitation_sum.sum(min_count=1),
                         precip_null_days=d.precipitation_sum.isna().sum(),
                         et0_30d_mm=d.et0_fao_evapotranspiration.sum(min_count=1),
                         fc_sm0_1_null_share=pd.Series(f["hourly"]["soil_moisture_0_to_1cm"], dtype=float).isna().mean()))
    df = pd.DataFrame(rows)
    df.to_csv(HERE / "openmeteo_fields.csv", index=False)
    print("openmeteo: distinct ERA5 cells", df.groupby(["era5_cell_lat", "era5_cell_lon"]).ngroups,
          "| distinct ICON cells", df.groupby(["icon_cell_lat", "icon_cell_lon"]).ngroups)
    return df


if __name__ == "__main__":
    RAW.mkdir(exist_ok=True)
    fields = load_fields()
    print(f"fields: {len(fields)} active, {fields.area_calc_ha.sum():.1f} ha")
    stages = sys.argv[1:] and [a for a in sys.argv[1:] if not a.startswith("--")] or \
        ["soilgrids", "nibis", "buek200", "dem", "openmeteo"]
    for st in stages:
        t0 = time.time()
        globals()[st](fields)
        print(f"  {st} done in {time.time()-t0:.0f}s", flush=True)
