# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "numpy", "rasterio", "pyproj"]
# ///
"""SoilGrids v2.0 as analysis-ready rasters for a bounding box, via ISRIC's WCS.

One multi-band GeoTIFF per property (bands = depth x statistic, named), in display units
(raw / d_factor), nodata = NaN, written in two flavours:

  utm250/<prop>.tif   native 250 m cells, warped to EPSG:32632 (nearest)
  s2grid/<prop>.tif   resampled (nearest) onto the Sentinel-2 10 m grid in
                      ../sentinel2/grid_and_params.json, so it stacks pixel-for-pixel with NDVI.
                      Values are still 250 m data: each SoilGrids cell is repeated, not refined.

Run from this folder:
  uv run soilgrids_rasters.py                       # Seggerde farm (bbox from the S2 grid)
  uv run soilgrids_rasters.py 9.9 52.1 10.1 52.3    # any lon/lat bbox: west south east north (utm250 only)

Downloads are cached in raw/ (native Homolosine GeoTIFFs as returned by the WCS).
WCS gotchas (see ../README.md): request the native grid with SUBSET=X(..)&SUBSET=Y(..) in metres
(a lat/lon subset comes back resampled); the GeoTIFFs carry no CRS and no nodata, 0 = no prediction.
"""
import json, sys, time
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyproj import Transformer
from rasterio.crs import CRS
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds

HERE = Path(__file__).parent
RAW = HERE / "raw"
IGH = CRS.from_proj4("+proj=igh +lon_0=0 +x_0=0 +y_0=0 +ellps=WGS84 +units=m +no_defs")
UTM = CRS.from_epsg(32632)
WCS = "https://maps.isric.org/mapserv?map=/map/{prop}.map"

PROPS = {  # d_factor, display unit
    "bdod": (100, "g/cm3"), "cec": (10, "cmol(c)/kg"), "cfvo": (10, "vol %"),
    "clay": (10, "%"), "sand": (10, "%"), "silt": (10, "%"), "nitrogen": (100, "g/kg"),
    "ocd": (10, "kg/m3"), "phh2o": (10, "pH"), "soc": (10, "g/kg"),
    "wv0010": (10, "vol %"), "wv0033": (10, "vol %"), "wv1500": (10, "vol %"),
    "ocs": (10, "kg/m2"),
}
DEPTHS = ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]
STATS = ["Q0.05", "Q0.5", "Q0.95", "mean", "uncertainty"]


def fetch(cov, prop, box):
    path = RAW / f"{cov}.tif"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        params = [("SERVICE", "WCS"), ("VERSION", "2.0.1"), ("REQUEST", "GetCoverage"), ("COVERAGEID", cov),
                  ("FORMAT", "image/tiff"), ("SUBSET", f"X({box[0]},{box[2]})"), ("SUBSET", f"Y({box[1]},{box[3]})")]
        for i in range(4):
            try:
                r = requests.get(WCS.format(prop=prop), params=params, timeout=120)
                if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image/tiff"):
                    path.write_bytes(r.content)
                    break
                print("  ", cov, r.status_code, r.text[:120])
            except requests.RequestException as e:
                print("  ", cov, e.__class__.__name__)
            time.sleep(3 * (i + 1))
        else:
            return None
    return path


def read_native(path, div, is_uncertainty):
    with rasterio.open(path) as src:
        a = src.read(1).astype("float32")
        a[a == 0] = np.nan  # 0 = no prediction
        return a / (10 if is_uncertainty else div), src.transform


def write(path, bands, names, transform, crs, unit, prop):
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = bands[0].shape
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=len(bands), dtype="float32",
                       crs=crs, transform=transform, nodata=np.nan, compress="deflate", predictor=3,
                       tiled=True, blockxsize=256, blockysize=256) as dst:
        for i, (b, n) in enumerate(zip(bands, names), 1):
            dst.write(b, i)
            dst.set_band_description(i, n)
        dst.update_tags(property=prop, unit=unit, source="ISRIC SoilGrids v2.0 (WCS)",
                        note="uncertainty bands = (Q0.95-Q0.05)/Q0.5, unitless; 250 m data")


def main():
    args = [float(a) for a in sys.argv[1:5]]
    s2 = json.loads((HERE.parent / "sentinel2" / "grid_and_params.json").read_text())
    if args:
        lonlat = args
        target = None
    else:
        lonlat = transform_bounds(s2["crs"], "EPSG:4326", *s2["bounds"])
        target = s2
    # bbox in Homolosine metres, padded by one cell so warping has full coverage at the edges
    to_igh = Transformer.from_crs("EPSG:4326", IGH, always_xy=True)
    xs, ys = zip(*[to_igh.transform(x, y) for x in lonlat[0::2] for y in lonlat[1::2]])
    box = (min(xs) - 500, min(ys) - 500, max(xs) + 500, max(ys) + 500)
    # common UTM 250 m grid covering the bbox
    ub = transform_bounds("EPSG:4326", UTM, *lonlat)
    x0, y1 = np.floor(ub[0] / 250) * 250, np.ceil(ub[3] / 250) * 250
    uw, uh = int(np.ceil((ub[2] - x0) / 250)), int(np.ceil((y1 - ub[1]) / 250))
    utm_tf = from_origin(x0, y1, 250, 250)

    summary = {}
    for prop, (div, unit) in PROPS.items():
        depths = ["0-30cm"] if prop == "ocs" else DEPTHS
        names, native = [], []
        for d in depths:
            for st in STATS:
                cov = f"{prop}_{d}_{st}"
                p = fetch(cov, prop, box)
                if p is None:
                    print("  missing", cov)
                    continue
                names.append(f"{d}_{st}")
                native.append(read_native(p, div, st == "uncertainty"))
        utm_bands, s2_bands = [], []
        for a, tf in native:
            dst = np.full((uh, uw), np.nan, "float32")
            reproject(a, dst, src_transform=tf, src_crs=IGH, dst_transform=utm_tf, dst_crs=UTM,
                      resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
            utm_bands.append(dst)
            if target:
                d2 = np.full((target["height"], target["width"]), np.nan, "float32")
                reproject(a, d2, src_transform=tf, src_crs=IGH, dst_transform=rasterio.Affine(*target["transform"][:6]),
                          dst_crs=target["crs"], resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
                s2_bands.append(d2)
        write(HERE / "utm250" / f"{prop}.tif", utm_bands, names, utm_tf, UTM, unit, prop)
        if target:
            write(HERE / "s2grid" / f"{prop}.tif", s2_bands, names, rasterio.Affine(*target["transform"][:6]),
                  CRS.from_string(target["crs"]), unit, prop)
        q50 = next((b for b, n in zip(utm_bands, names) if n.endswith("Q0.5")), None)
        summary[prop] = dict(bands=len(names), unit=unit,
                             nan_share_top=float(np.isnan(q50).mean()) if q50 is not None else None,
                             q50_top_min=float(np.nanmin(q50)) if q50 is not None and np.isfinite(q50).any() else None,
                             q50_top_max=float(np.nanmax(q50)) if q50 is not None and np.isfinite(q50).any() else None)
        print(f"{prop:9s} {len(names):2d} bands  {summary[prop]}", flush=True)
    (HERE / "summary.json").write_text(json.dumps(dict(bbox_lonlat=list(lonlat), utm250_shape=[uh, uw],
                                                       s2grid=bool(target), props=summary), indent=1))


if __name__ == "__main__":
    main()
