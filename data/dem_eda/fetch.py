# /// script
# requires-python = ">=3.10"
# dependencies = ["rasterio", "numpy", "pystac-client"]
# ///
"""EDA fetch for Copernicus DEM GLO-30 (DSM, 1 arc-second) at the hackathon test sites.

Run:   uv run data/dem_eda/fetch.py            (from repo root)
Output (next to this script):
  raw/<site>_window.npy / .tif   15x15 float32 elevation window centred on the point
  raw/stac_<tile>.json           STAC item used for each tile
  dem_sites.csv                  per-site elevation / slope / aspect / relief / TPI / latency / bytes
  raw/run_log.json               full per-site record (incl. errors)

Only HTTP range reads of a small window are done (never the full tile).
"""
from __future__ import annotations

import csv
import json
import logging
import math
import re
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RAW.mkdir(parents=True, exist_ok=True)

STAC_URL = "https://earth-search.aws.element84.com/v1"
COLLECTION = "cop-dem-glo-30"
BUCKET_HTTPS = "https://copernicus-dem-30m.s3.amazonaws.com"

SITES = [
    ("hildesheimer_boerde", "Hildesheimer Börde (loess)", 9.95, 52.22),
    ("lueneburger_heide", "Lüneburger Heide (sand)", 10.05, 53.05),
    ("emsland", "Emsland (sand/peat)", 7.35, 52.75),
    ("wesermarsch", "Wesermarsch (marsh clay)", 8.40, 53.35),
    ("teufelsmoor", "Teufelsmoor (bog)", 8.90, 53.25),
    ("solling", "Solling (upland forest)", 9.55, 51.75),
    ("hannover_centre", "Hannover centre (urban)", 9.73, 52.37),
    ("hamburg", "Hamburg", 9.95, 53.55),
]

HALF = 7  # window = (2*HALF+1)^2 = 15x15 px  (~460 m N-S, ~420 m E-W at 52-53 N)
FLAT_DEG = 0.1  # below this slope, aspect is reported as "flat"

GDAL_ENV = dict(
    AWS_NO_SIGN_REQUEST="YES",
    GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",  # don't LIST the bucket "directory"
    CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
    GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES",
    GDAL_HTTP_MULTIPLEX="YES",
    # disable the process-wide vsicurl cache so every site is measured "cold"
    CPL_VSIL_CURL_NON_CACHED=f"/vsicurl/{BUCKET_HTTPS}/",
    CPL_DEBUG="ON",  # needed to capture "Downloading a-b" lines for byte accounting
)


# ----------------------------------------------------------------- byte accounting
class RangeCounter(logging.Handler):
    """Collects GDAL VSICURL 'Downloading <start>-<end>' debug lines routed via rasterio."""

    pat = re.compile(r"Downloading (\d+)-(\d+)")

    def __init__(self):
        super().__init__(logging.DEBUG)
        self.reset()

    def reset(self):
        self.ranges: list[tuple[int, int]] = []

    def emit(self, record):
        m = self.pat.search(record.getMessage())
        if m:
            self.ranges.append((int(m.group(1)), int(m.group(2))))

    @property
    def nbytes(self):
        return sum(b - a + 1 for a, b in self.ranges)


counter = RangeCounter()
for name in ("rasterio", "rasterio._env", "rasterio._base", "rasterio._io"):
    lg = logging.getLogger(name)
    lg.setLevel(logging.DEBUG)
    lg.addHandler(counter)
    lg.propagate = False


# ----------------------------------------------------------------- tile naming
def tile_name(lon: float, lat: float) -> str:
    """Direct bucket tile name. Tile N52 covers lat [52,53), E009 covers lon [9,10)
    (named by the SW integer corner; pixel *centres* sit on the integer degree lines)."""
    la, lo = math.floor(lat), math.floor(lon)
    ns = f"N{la:02d}" if la >= 0 else f"S{-la:02d}"
    ew = f"E{lo:03d}" if lo >= 0 else f"W{-lo:03d}"
    return f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"


def direct_url(lon: float, lat: float) -> str:
    t = tile_name(lon, lat)
    return f"{BUCKET_HTTPS}/{t}/{t}.tif"


def s3_to_https(href: str) -> str:
    # STAC asset hrefs are s3://copernicus-dem-30m/...  -> public https endpoint
    return href.replace("s3://copernicus-dem-30m/", BUCKET_HTTPS + "/")


# ----------------------------------------------------------------- geometry
A_WGS84 = 6378137.0
E2_WGS84 = 6.69437999014e-3


def pixel_size_m(dlon_deg: float, dlat_deg: float, lat: float) -> tuple[float, float]:
    """Metres per pixel on the WGS84 ellipsoid at latitude `lat`."""
    phi = math.radians(lat)
    s = math.sin(phi) ** 2
    N = A_WGS84 / math.sqrt(1 - E2_WGS84 * s)  # prime-vertical radius
    M = A_WGS84 * (1 - E2_WGS84) / (1 - E2_WGS84 * s) ** 1.5  # meridional radius
    return math.radians(dlon_deg) * N * math.cos(phi), math.radians(dlat_deg) * M


def horn(z3: np.ndarray, dx: float, dy: float) -> tuple[float, float, float]:
    """Horn (1981) 3x3 gradient. z3 rows go north->south, cols west->east.
    Returns slope_deg, slope_pct, aspect_deg (compass bearing of downslope direction,
    0=N, 90=E; NaN if flat)."""
    a, b, c = z3[0]
    d, _, f = z3[1]
    g, h, i = z3[2]
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * dx)  # + = rises to the east
    dzdy = ((a + 2 * b + c) - (g + 2 * h + i)) / (8 * dy)  # + = rises to the north
    grad = math.hypot(dzdx, dzdy)
    slope_deg = math.degrees(math.atan(grad))
    if slope_deg < FLAT_DEG:
        aspect = float("nan")
    else:
        aspect = (math.degrees(math.atan2(-dzdx, -dzdy)) + 360) % 360
    return slope_deg, 100 * grad, aspect


def compass(aspect: float) -> str:
    if math.isnan(aspect):
        return "flat"
    labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return labels[int(((aspect + 22.5) % 360) // 45)]


# ----------------------------------------------------------------- STAC
def stac_item(lon: float, lat: float):
    from pystac_client import Client

    t0 = time.perf_counter()
    cat = Client.open(STAC_URL)
    items = list(
        cat.search(collections=[COLLECTION], intersects={"type": "Point", "coordinates": [lon, lat]}, max_items=5).items()
    )
    dt = time.perf_counter() - t0
    return items, dt


# ----------------------------------------------------------------- per-site
def process(site_id, label, lon, lat):
    rec = dict(site_id=site_id, label=label, lon=lon, lat=lat)
    items, t_stac = stac_item(lon, lat)
    rec["stac_ms"] = round(1000 * t_stac)
    rec["stac_n_items"] = len(items)
    if not items:
        rec["error"] = "no STAC item"
        return rec
    # tile bboxes overlap by half a pixel; choose the one whose id matches the SW-corner rule
    want = tile_name(lon, lat)
    item = next((it for it in items if it.id == want), items[0])
    rec["tile"] = item.id
    (RAW / f"stac_{item.id}.json").write_text(json.dumps(item.to_dict(), indent=1))
    url = s3_to_https(item.assets["data"].href)
    assert url == direct_url(lon, lat), (url, direct_url(lon, lat))
    rec["url"] = url

    counter.reset()
    t0 = time.perf_counter()
    with rasterio.Env(**GDAL_ENV):
        with rasterio.open(url) as src:
            t_open = time.perf_counter() - t0
            T = src.transform
            dlon, dlat = T.a, -T.e
            # fractional pixel coords (pixel-centre convention: centre of px (0,0) at col=0.0)
            colf = (lon - T.c) / dlon - 0.5
            rowf = (T.f - lat) / dlat - 0.5
            c0, r0 = int(round(colf)), int(round(rowf))  # nearest pixel
            win = Window(c0 - HALF, r0 - HALF, 2 * HALF + 1, 2 * HALF + 1)
            if win.col_off < 0 or win.row_off < 0 or win.col_off + win.width > src.width or win.row_off + win.height > src.height:
                rec["error"] = "window crosses tile edge (needs neighbour tile mosaic)"
                return rec
            z = src.read(1, window=win).astype("float64")
            wtransform = src.window_transform(win)
            profile = src.profile
    t_total = time.perf_counter() - t0
    rec.update(
        open_ms=round(1000 * t_open),
        read_ms=round(1000 * (t_total - t_open)),
        total_ms=round(1000 * t_total),
        http_ranges=len(counter.ranges),
        bytes_read=counter.nbytes,
    )
    if not np.isfinite(z).all():
        rec["warning"] = "non-finite values in window"

    # save raw window
    np.save(RAW / f"{site_id}_window.npy", z.astype("float32"))
    prof = dict(profile)
    prof.update(width=z.shape[1], height=z.shape[0], transform=wtransform, tiled=False)
    prof.pop("blockxsize", None), prof.pop("blockysize", None)
    with rasterio.open(RAW / f"{site_id}_window.tif", "w", **prof) as dst:
        dst.write(z.astype("float32"), 1)

    c = HALF  # centre index in window
    # bilinear at the exact point
    fx, fy = colf - c0 + c, rowf - r0 + c
    x0, y0 = int(math.floor(fx)), int(math.floor(fy))
    tx, ty = fx - x0, fy - y0
    bil = (
        z[y0, x0] * (1 - tx) * (1 - ty)
        + z[y0, x0 + 1] * tx * (1 - ty)
        + z[y0 + 1, x0] * (1 - tx) * ty
        + z[y0 + 1, x0 + 1] * tx * ty
    )
    dx, dy = pixel_size_m(dlon, dlat, lat)
    sdeg, spct, asp = horn(z[c - 1 : c + 2, c - 1 : c + 2], dx, dy)

    # slope over the whole window (Horn on every interior pixel) for context
    slopes = []
    for r in range(1, z.shape[0] - 1):
        for k in range(1, z.shape[1] - 1):
            slopes.append(horn(z[r - 1 : r + 2, k - 1 : k + 2], dx, dy)[0])
    slopes = np.array(slopes)

    # robust ("smoothed") slope: 3x3 mean filter, then Horn with a 3-pixel step
    # (neighbours ~85-93 m away) -> damps single-pixel canopy/building steps
    zs = sum(z[1 + i : z.shape[0] - 1 + i, 1 + j : z.shape[1] - 1 + j] for i in (-1, 0, 1) for j in (-1, 0, 1)) / 9.0
    cs = c - 1  # centre index in zs
    z3s = zs[cs - 3 : cs + 4 : 3, cs - 3 : cs + 4 : 3]
    ssm_deg, ssm_pct, asp_sm = horn(z3s, 3 * dx, 3 * dy)
    # DSM artefact heuristic: >5 m step between the centre and any 8-neighbour
    step = float(np.abs(z[c - 1 : c + 2, c - 1 : c + 2] - z[c, c]).max())
    flag = step > 5.0 or (sdeg > 5 and sdeg > 2.5 * max(ssm_deg, 1.0))

    z5 = z[c - 2 : c + 3, c - 2 : c + 3]
    ring = np.delete(z.ravel(), z.size // 2)  # all but centre
    rec.update(
        pixel_dx_m=round(dx, 2),
        pixel_dy_m=round(dy, 2),
        window_px=f"{z.shape[1]}x{z.shape[0]}",
        elev_nearest_m=round(float(z[c, c]), 2),
        elev_bilinear_m=round(float(bil), 2),
        slope_deg=round(sdeg, 2),
        slope_pct=round(spct, 2),
        aspect_deg=None if math.isnan(asp) else round(asp, 1),
        aspect_label=compass(asp),
        relief_5x5_m=round(float(z5.max() - z5.min()), 2),
        relief_15x15_m=round(float(z.max() - z.min()), 2),
        win_min_m=round(float(z.min()), 2),
        win_max_m=round(float(z.max()), 2),
        win_std_m=round(float(z.std()), 2),
        tpi_15x15_m=round(float(z[c, c] - ring.mean()), 2),
        slope_win_median_deg=round(float(np.median(slopes)), 2),
        slope_win_max_deg=round(float(slopes.max()), 2),
        slope_smooth90_deg=round(ssm_deg, 2),
        aspect_smooth90_deg=None if math.isnan(asp_sm) else round(asp_sm, 1),
        aspect_smooth90_label=compass(asp_sm),
        max_step_3x3_m=round(step, 2),
        dsm_artifact_suspect=flag,
    )
    rec.update(read_aux(url, lon, lat))
    return rec


AUX = {  # AUXFILES that sit next to every DEM tile (same 1"x1.5" grid)
    "WBM": "wbm",  # water body mask uint8; 0 = no water (other codes: ocean/lake/river, see Copernicus DEM Product Handbook)
    "HEM": "hem_m",  # height error map, float32 metres; -32767 (nodata) on edited pixels -> reported as None
    "EDM": "edm",  # editing mask uint8; raw code (not decoded here), observed 1 where HEM valid, 2-4 where HEM nodata
}


def read_aux(url: str, lon: float, lat: float) -> dict:
    """Centre-pixel value from the auxiliary masks (1 small range read each)."""
    out = {}
    tile = url.rsplit("/", 1)[0]
    name = url.rsplit("/", 1)[1].replace("_DEM.tif", "")
    t0 = time.perf_counter()
    for code, key in AUX.items():
        aux_url = f"{tile}/AUXFILES/{name}_{code}.tif"
        try:
            with rasterio.Env(**GDAL_ENV), rasterio.open(aux_url) as a:
                r, k = a.index(lon, lat)
                v = a.read(1, window=Window(k, r, 1, 1))[0, 0]
                if a.dtypes[0].startswith("float"):
                    out[key] = None if v <= -32767 else round(float(v), 3)
                else:
                    out[key] = int(v)
        except Exception as e:
            out[key] = None
            out[f"{key}_error"] = f"{type(e).__name__}: {e}"
    out["aux_ms"] = round(1000 * (time.perf_counter() - t0))
    return out


def main():
    rows = []
    for s in SITES:
        try:
            rec = process(*s)
        except Exception as e:  # record failures, never invent values
            rec = dict(site_id=s[0], label=s[1], lon=s[2], lat=s[3], error=f"{type(e).__name__}: {e}")
        print(json.dumps(rec, ensure_ascii=False))
        rows.append(rec)

    (RAW / "run_log.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    keys = []
    for r in rows:
        keys += [k for k in r if k not in keys]
    with open(HERE / "dem_sites.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
