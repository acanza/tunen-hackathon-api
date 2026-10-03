# /// script
# requires-python = ">=3.11"
# dependencies = ["pystac-client", "rasterio", "numpy", "pandas", "shapely", "pyproj"]
# ///
"""Sentinel-2 L2A NDVI history for the LuF Seggerde farm (bbox only, no field polygons).

    uv run fetch_s2.py                      # all seasons 2019..2026
    uv run fetch_s2.py --years 2026         # refresh one season (14-day job)

Steps
1. STAC search (Element84 Earth Search v1, `sentinel-2-l2a`) per season (Mar-Oct),
   eo:cloud_cover < 60. Item JSONs -> raw/items/.
2. Group items into observations = (acquisition date, platform). Per MGRS tile keep the
   item with the highest processing baseline / sequence (Earth Search has `_0` and
   reprocessed `_1` items for older dates). Tiles are ordered by footprint coverage of the
   farm window; the first is read, the next only fills its nodata gaps.
3. Windowed COG reads (HTTP range requests) of SCL (20 m) first; scenes below
   MIN_VALID are dropped without reading red/nir. Then B04 + B08 (10 m).
4. BOA offset: subtract 1000 DN only when baseline >= 04.00 AND
   `earthsearch:boa_offset_applied` is False (see README: on Earth Search the offset is
   already applied in the COG pixels, despite raster:bands offset = -0.1).
5. NDVI = (nir - red)/(nir + red) on masked pixels; per-season int16 stacks
   (ndvi_stack_<year>.tif, NDVI*10000, nodata -32768, band description = obs id),
   per-season peak composite ndvi_peak_<year>.tif (p90, max, n_obs over May-Jul),
   scene_catalogue.csv.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

os.environ.update(
    AWS_NO_SIGN_REQUEST="YES",
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    GDAL_HTTP_MULTIPLEX="YES",
    GDAL_HTTP_MAX_RETRY="3",
    GDAL_HTTP_RETRY_DELAY="2",
    VSI_CACHE="FALSE",
)

import numpy as np
import pandas as pd
import rasterio
from pyproj import Transformer
from pystac_client import Client
from rasterio.transform import from_origin
from rasterio.windows import from_bounds
from shapely.geometry import box, shape
from shapely.ops import transform as shp_transform

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw" / "items"
STAC = "https://earth-search.aws.element84.com/v1"
COLLECTION = "sentinel-2-l2a"

FARM_BBOX = (11.025, 52.315, 11.122, 52.390)  # lon/lat, from fields_active.geojson
PAD_M = 200
CRS = "EPSG:32632"  # all items over the farm report proj:epsg 32632 (checked per item)
RES = 10
SNAP = 20  # snap the grid to 20 m so the 20 m SCL pixels map exactly onto 2x2 10 m pixels

MAX_CLOUD = 60
MIN_VALID = 0.20  # scene kept if >= 20 % of the farm window is clear after SCL masking
PEAK_MONTHS = (5, 6, 7)
KEEP_SCL = (4, 5, 6)  # vegetation, not vegetated (bare soil), water
CLOUDY_SCL = (3, 8, 9, 10)  # cloud shadow, cloud medium, cloud high, thin cirrus -> dilated
DILATE_PX20 = 2  # 2 x 20 m = 40 m buffer around cloud/shadow
SCL_NAMES = {0: "no_data", 1: "saturated_defective", 2: "dark_area", 3: "cloud_shadow",
             4: "vegetation", 5: "not_vegetated", 6: "water", 7: "unclassified",
             8: "cloud_medium", 9: "cloud_high", 10: "thin_cirrus", 11: "snow"}


def farm_grid():
    t = Transformer.from_crs(4326, CRS, always_xy=True)
    lon0, lat0, lon1, lat1 = FARM_BBOX
    xs, ys = t.transform([lon0, lon1, lon0, lon1], [lat0, lat0, lat1, lat1])
    x0 = math.floor((min(xs) - PAD_M) / SNAP) * SNAP
    y0 = math.floor((min(ys) - PAD_M) / SNAP) * SNAP
    x1 = math.ceil((max(xs) + PAD_M) / SNAP) * SNAP
    y1 = math.ceil((max(ys) + PAD_M) / SNAP) * SNAP
    width, height = (x1 - x0) // RES, (y1 - y0) // RES
    return (x0, y0, x1, y1), from_origin(x0, y1, RES, RES), width, height


BOUNDS, TRANSFORM, W, H = farm_grid()
_to_ll = Transformer.from_crs(CRS, 4326, always_xy=True)
GRID_LL = shp_transform(lambda x, y: _to_ll.transform(x, y), box(*BOUNDS))


def baseline_num(item) -> float:
    try:
        return float(item.properties.get("s2:processing_baseline", "0"))
    except ValueError:
        return 0.0


def dn_offset(item) -> int:
    """DN to subtract before scaling by 1e-4 (0 or 1000)."""
    applied = item.properties.get("earthsearch:boa_offset_applied")
    if baseline_num(item) >= 4.0 and applied is False:
        return 1000
    return 0


def search(cat, year: int):
    end = min(date(year, 10, 31), date.today())
    items = list(cat.search(collections=[COLLECTION], bbox=FARM_BBOX,
                            datetime=f"{year}-03-01/{end.isoformat()}",
                            query={"eo:cloud_cover": {"lt": MAX_CLOUD}}).items())
    return items


def group_observations(items):
    obs = {}
    for it in items:
        d = it.datetime.date().isoformat()
        plat = it.properties.get("platform", it.id[:3])
        obs.setdefault((d, plat), []).append(it)
    out = []
    for (d, plat), its in sorted(obs.items()):
        best = {}
        for it in its:
            tile = it.properties.get("grid:code", it.id.split("_")[1])
            seq = int(it.properties.get("s2:sequence", it.id.split("_")[3]) or 0)
            k = (baseline_num(it), seq)
            if tile not in best or k > best[tile][0]:
                best[tile] = (k, it)
        tiles = []
        for tile, (_, it) in best.items():
            cov = shape(it.geometry).intersection(GRID_LL).area / GRID_LL.area
            tiles.append((cov, tile, it))
        tiles.sort(key=lambda x: -x[0])
        out.append(dict(obs_id=f"{d}_{plat}", date=d, platform=plat, tiles=tiles,
                        n_candidates=len(its)))
    return out


def read_window(href: str, res: int) -> np.ndarray:
    for attempt in range(3):
        try:
            with rasterio.open(href) as src:
                assert src.crs.to_epsg() == 32632, f"unexpected CRS {src.crs}"
                assert abs(src.transform.a - res) < 1e-6
                win = from_bounds(*BOUNDS, transform=src.transform).round_offsets().round_lengths()
                return src.read(1, window=win, boundless=True, fill_value=0)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2 * (attempt + 1))


def dilate(mask: np.ndarray, n: int) -> np.ndarray:
    out = mask.copy()
    for _ in range(n):
        m = out.copy()
        m[1:, :] |= out[:-1, :]; m[:-1, :] |= out[1:, :]
        m[:, 1:] |= out[:, :-1]; m[:, :-1] |= out[:, 1:]
        out = m
    return out


def process(ob):
    t0 = time.time()
    rec = dict(obs_id=ob["obs_id"], date=ob["date"], platform=ob["platform"],
               n_candidate_items=ob["n_candidates"])
    scl = np.zeros((H // 2, W // 2), np.uint8)
    used = []
    for cov, tile, it in ob["tiles"]:
        if (scl > 0).all():
            break
        s = read_window(it.assets["scl"].href, 20)
        fill = (scl == 0) & (s > 0)
        if fill.any():
            scl[fill] = s[fill]
            used.append((tile, it, fill))
    rec.update(items=";".join(u[1].id for u in used), tiles=";".join(u[0] for u in used),
               baselines=";".join(u[1].properties.get("s2:processing_baseline", "") for u in used),
               boa_offset_applied=";".join(str(u[1].properties.get("earthsearch:boa_offset_applied")) for u in used),
               dn_offset_subtracted=";".join(str(dn_offset(u[1])) for u in used),
               eo_cloud_cover=";".join(f"{u[1].properties.get('eo:cloud_cover', float('nan')):.1f}" for u in used),
               tile_coverage=";".join(f"{c:.3f}" for c, *_ in ob["tiles"]))
    n = scl.size
    rec["nodata_frac"] = float((scl == 0).mean())
    for k, name in SCL_NAMES.items():
        rec[f"scl_{name}"] = round(float((scl == k).sum()) / n, 4)
    clear = np.isin(scl, KEEP_SCL) & ~dilate(np.isin(scl, CLOUDY_SCL), DILATE_PX20)
    rec["valid_frac"] = round(float(clear.mean()), 4)
    if rec["valid_frac"] < MIN_VALID:
        rec.update(used=False, reason=f"valid_frac<{MIN_VALID}", seconds=round(time.time() - t0, 2))
        return rec, None
    red = np.zeros((H, W), np.float32)
    nir = np.zeros((H, W), np.float32)
    for tile, it, fill20 in used:
        fill = np.repeat(np.repeat(fill20, 2, 0), 2, 1)
        off = dn_offset(it)
        r = read_window(it.assets["red"].href, 10).astype(np.float32)
        n_ = read_window(it.assets["nir"].href, 10).astype(np.float32)
        red[fill] = np.where(r[fill] > 0, r[fill] - off, 0)
        nir[fill] = np.where(n_[fill] > 0, n_[fill] - off, 0)
    clear10 = np.repeat(np.repeat(clear, 2, 0), 2, 1) & (red > 0) & (nir > 0)
    ndvi = np.full((H, W), np.nan, np.float32)
    ndvi[clear10] = (nir[clear10] - red[clear10]) / (nir[clear10] + red[clear10])
    veg = clear10 & (np.repeat(np.repeat(scl == 4, 2, 0), 2, 1))
    rec["red_dn_p50_veg"] = float(np.median(red[veg])) if veg.any() else np.nan
    rec["nir_dn_p50_veg"] = float(np.median(nir[veg])) if veg.any() else np.nan
    rec["ndvi_p50_window"] = float(np.nanmedian(ndvi)) if clear10.any() else np.nan
    rec.update(used=True, reason="", seconds=round(time.time() - t0, 2))
    return rec, ndvi


def write_tif(path, arrays, dtype, nodata, descriptions):
    prof = dict(driver="GTiff", width=W, height=H, count=len(arrays), dtype=dtype, crs=CRS,
                transform=TRANSFORM, nodata=nodata, compress="deflate", predictor=2,
                tiled=True, blockxsize=256, blockysize=256)
    if dtype.startswith("float"):
        prof["predictor"] = 3
    with rasterio.open(path, "w", **prof) as dst:
        for i, (a, d) in enumerate(zip(arrays, descriptions), 1):
            dst.write(a.astype(dtype), i)
            dst.set_band_description(i, d)


def run_season(cat, year, workers, log):
    t0 = time.time()
    items = search(cat, year)
    log(f"{year}: {len(items)} items (cloud<{MAX_CLOUD}) in {time.time() - t0:.1f}s")
    for it in items:
        epsg = it.properties.get("proj:epsg") or it.properties.get("proj:code")
        if str(epsg) not in ("32632", "EPSG:32632"):
            log(f"  WARNING {it.id} has CRS {epsg}, skipped")
        p = RAW / f"{it.id}.json"
        if not p.exists():
            p.write_text(json.dumps(it.to_dict()))
    items = [it for it in items if str(it.properties.get("proj:epsg") or it.properties.get("proj:code")) in ("32632", "EPSG:32632")]
    obs = group_observations(items)
    recs, ndvis = [], {}
    with ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(process, ob): ob for ob in obs}
        for f in as_completed(futs):
            ob = futs[f]
            try:
                rec, nd = f.result()
            except Exception as e:  # record, never invent
                rec, nd = dict(obs_id=ob["obs_id"], date=ob["date"], platform=ob["platform"],
                               used=False, reason=f"error: {type(e).__name__}: {e}"[:300]), None
            rec["season"] = year
            recs.append(rec)
            if nd is not None:
                ndvis[rec["obs_id"]] = nd
    order = sorted(ndvis)
    log(f"{year}: {len(obs)} observations, {len(order)} used, {time.time() - t0:.0f}s")
    if order:
        stack = [np.where(np.isnan(ndvis[k]), -32768, np.round(ndvis[k] * 10000)) for k in order]
        write_tif(HERE / f"ndvi_stack_{year}.tif", stack, "int16", -32768, order)
        peak = [k for k in order if int(k[5:7]) in PEAK_MONTHS]
        if peak:
            arr = np.stack([ndvis[k] for k in peak])
            nobs = np.isfinite(arr).sum(0)
            with np.errstate(all="ignore"), __import__("warnings").catch_warnings():
                __import__("warnings").simplefilter("ignore")
                p90 = np.nanpercentile(arr, 90, axis=0)
                mx = np.nanmax(arr, axis=0)
            write_tif(HERE / f"ndvi_peak_{year}.tif",
                      [np.where(nobs > 0, p90, np.nan), np.where(nobs > 0, mx, np.nan), nobs.astype(np.float32)],
                      "float32", np.nan, ["ndvi_p90_MayJul", "ndvi_max_MayJul", "n_valid_obs_MayJul"])
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, nargs="*", default=list(range(2019, 2027)))
    ap.add_argument("--workers", type=int, default=6)
    a = ap.parse_args()
    RAW.mkdir(parents=True, exist_ok=True)
    logf = open(HERE / "fetch_log.txt", "a")

    def log(msg):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        print(line, flush=True)
        logf.write(line + "\n"); logf.flush()

    log(f"grid {CRS} bounds={BOUNDS} {W}x{H} px @ {RES} m; years={a.years}")
    cat = Client.open(STAC)
    cat_path = HERE / "scene_catalogue.csv"
    old = pd.read_csv(cat_path) if cat_path.exists() else pd.DataFrame()
    for year in a.years:
        recs = run_season(cat, year, a.workers, log)
        new = pd.DataFrame(recs)
        if not old.empty:
            old = old[old["season"] != year]
        old = pd.concat([old, new], ignore_index=True).sort_values(["date", "platform"])
        old.to_csv(cat_path, index=False)
    json.dump(dict(crs=CRS, bounds=BOUNDS, transform=list(TRANSFORM)[:6], width=W, height=H,
                   max_cloud=MAX_CLOUD, min_valid=MIN_VALID, keep_scl=KEEP_SCL,
                   cloudy_scl_dilated=CLOUDY_SCL, dilate_m=DILATE_PX20 * 20,
                   peak_months=PEAK_MONTHS, run=time.strftime("%Y-%m-%dT%H:%M:%S")),
              open(HERE / "grid_and_params.json", "w"), indent=1)
    log("done")


if __name__ == "__main__":
    main()
