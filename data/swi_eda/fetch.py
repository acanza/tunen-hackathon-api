# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pandas", "numpy", "geopandas", "shapely", "rasterio", "exactextract"]
# ///
"""Pull Copernicus CLMS Soil Water Index (SWI) Europe 1 km daily v2 for the LuF Seggerde farm fields.

SWI is derived from Sentinel-1 (C-SAR) + Metop ASCAT ("SCATSAR") surface soil moisture, propagated
into the profile with an exponential filter. Each T value (002..100, in days) is a characteristic
time length: small T = topsoil, large T = deeper / slower layers.

Needs a free Copernicus Data Space Ecosystem (CDSE) account. Credentials are read from the env vars
CDSE_USERNAME / CDSE_PASSWORD, or from a .env file at the repo root (gitignored).

Run from this folder:  uv run fetch.py              (last 30 days available, cached crops reused)
                       uv run fetch.py --days 60
                       uv run fetch.py --force      (re-download everything)

Outputs:
  raw/stac_items.json            STAC search response (catalogue, no auth)
  raw/crops/<date>_<asset>.tif   farm window cut from the Europe-wide COG (original uint8 values)
  swi_pixels.csv                 date, asset, lon, lat, raw value, scaled value  (every pixel in window)
  swi_fields.csv                 plotId, date, asset, coverage-weighted mean, n pixel equivalents
"""
import json, os, sys, time
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import requests
from exactextract import exact_extract
from rasterio.windows import from_bounds

HERE = Path(__file__).parent
RAW = HERE / "raw"
REPO = HERE.parent.parent
FIELDS_SRC = REPO / "LuF-Seggerde-Dev-fields.geojson"
FORCE = "--force" in sys.argv
DAYS = int(sys.argv[sys.argv.index("--days") + 1]) if "--days" in sys.argv else 30
UA = {"User-Agent": "tunen-hackathon-eda/0.1"}
STAC = "https://catalogue.dataspace.copernicus.eu/stac/collections/clms_swi_europe_1km_daily_v2_cog/items"
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
ASSETS = ["swi002", "swi005", "swi010", "swi020", "swi040", "swi060", "swi100", "qflag010", "ssf"]
SCALE = {a: 0.5 for a in ASSETS if a.startswith("swi")}  # STAC raster:scale; SWI in %
PAD_DEG = 0.02  # ~2 pixels around the farm bbox


def creds():
    env = {}
    if (REPO / ".env").exists():
        for line in (REPO / ".env").read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    u = os.environ.get("CDSE_USERNAME") or env.get("CDSE_USERNAME")
    p = os.environ.get("CDSE_PASSWORD") or env.get("CDSE_PASSWORD")
    if not (u and p):
        sys.exit("set CDSE_USERNAME / CDSE_PASSWORD (env or repo-root .env); register at dataspace.copernicus.eu")
    return u, p


class Token:
    """CDSE access tokens live 10 min; refresh a bit early."""
    def __init__(self):
        self.user, self.pw = creds()
        self.value, self.expires = None, 0

    def __call__(self):
        if time.time() > self.expires - 60:
            r = requests.post(TOKEN_URL, data=dict(client_id="cdse-public", grant_type="password",
                                                   username=self.user, password=self.pw), timeout=30)
            if r.status_code != 200:
                sys.exit(f"CDSE login failed: HTTP {r.status_code} {r.text[:200]}")
            js = r.json()
            self.value, self.expires = js["access_token"], time.time() + js["expires_in"]
        return self.value


def load_fields():
    g = gpd.read_file(FIELDS_SRC)
    g["geometry"] = g.geometry.make_valid()
    return g[~g.isArchived].reset_index(drop=True)[["plotId", "fieldName", "geometry"]]


def stac_items(bbox):
    start = (date.today() - timedelta(days=DAYS)).isoformat()
    feats, url = [], STAC
    params = dict(bbox=",".join(map(str, bbox)), datetime=f"{start}T00:00:00Z/..", limit=100)
    while url:
        js = requests.get(url, params=params, headers=UA, timeout=60).json()
        feats += js["features"]
        url, params = next((l["href"] for l in js.get("links", []) if l["rel"] == "next"), None), None
    (RAW / "stac_items.json").write_text(json.dumps(feats, indent=1))
    return feats


def crop(href, out, bounds, token):
    """Windowed read over HTTP range requests; fall back to full download if ranges are refused."""
    hdr = f"Authorization: Bearer {token()}"
    try:
        with rasterio.Env(GDAL_HTTP_HEADERS=hdr, GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
                          CPL_VSIL_CURL_ALLOWED_EXTENSIONS="", GDAL_HTTP_MAX_RETRY=3), \
                rasterio.open(f"/vsicurl/{href}") as src:
            return write_window(src, out, bounds), "range"
    except rasterio.errors.RasterioIOError as e:
        print("  range read failed, downloading full file:", str(e)[:120], flush=True)
    tmp = out.with_suffix(".full.tif")
    with requests.get(href, headers={"Authorization": f"Bearer {token()}", **UA}, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
    with rasterio.open(tmp) as src:
        write_window(src, out, bounds)
    tmp.unlink()
    return out, "full"


def write_window(src, out, bounds):
    win = from_bounds(*bounds, src.transform).round_offsets().round_lengths()
    a = src.read(1, window=win)
    prof = src.profile | dict(height=a.shape[0], width=a.shape[1], transform=src.window_transform(win),
                              driver="GTiff", tiled=False, compress="deflate")
    prof.pop("blockxsize", None); prof.pop("blockysize", None)
    out.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out, "w", **prof) as dst:
        dst.write(a, 1)
    return out


def main():
    RAW.mkdir(exist_ok=True)
    fields = load_fields()
    w, s, e, n = fields.total_bounds
    bounds = (w - PAD_DEG, s - PAD_DEG, e + PAD_DEG, n + PAD_DEG)
    items = stac_items([w, s, e, n])
    print(f"swi: {len(items)} daily products since {DAYS} days ago", flush=True)
    token = Token()
    pix, zon, modes = [], [], {}
    for it in sorted(items, key=lambda i: i["id"]):
        day = it["id"].split("_")[2][:8]  # product date from the id; STAC datetime is 1 day earlier
        for a in ASSETS:
            if a not in it["assets"]:
                continue
            out = RAW / "crops" / f"{day}_{a}.tif"
            if FORCE or not out.exists():
                _, mode = crop(it["assets"][a]["alternate"]["https"]["href"], out, bounds, token)
                modes[mode] = modes.get(mode, 0) + 1
            with rasterio.open(out) as src:
                v = src.read(1).astype("float64")
                nodata = src.nodata
                rows, cols = np.indices(v.shape)
                xs, ys = rasterio.transform.xy(src.transform, rows.ravel(), cols.ravel())
            scale = SCALE.get(a, 1)
            valid = (v != nodata) & ((v <= 200) if a in SCALE else True)  # SWI codes >200 are flags
            pix.append(pd.DataFrame(dict(date=day, asset=a, lon=np.round(xs, 5), lat=np.round(ys, 5),
                                         raw=v.ravel(), value=np.where(valid, v * scale, np.nan).ravel())))
            if a in SCALE:
                scaled = out.with_name(out.stem + "_scaled.tif")  # float copy with flags -> NaN for zonal
                with rasterio.open(out) as src:
                    prof = src.profile | dict(dtype="float32", nodata=np.nan)
                    with rasterio.open(scaled, "w", **prof) as dst:
                        dst.write(np.where(valid, v * scale, np.nan).astype("float32"), 1)
                ex = exact_extract(str(scaled), fields, ["mean", "count", "min", "max"], output="pandas")
                scaled.unlink()
                zon.append(pd.DataFrame(dict(plotId=fields.plotId, fieldName=fields.fieldName, date=day,
                                             asset=a, mean=ex["mean"], min=ex["min"], max=ex["max"],
                                             valid_pixel_equiv=ex["count"])))
    pd.concat(pix).to_csv(HERE / "swi_pixels.csv", index=False)
    z = pd.concat(zon)
    z.round(3).to_csv(HERE / "swi_fields.csv", index=False)
    print("swi: downloads by mode", modes or "(all cached)")
    piv = z[z.asset == "swi010"].groupby("date")["mean"].agg(["count", "min", "median", "max"])
    print("swi010 per day across fields (count = fields with a value):\n" + piv.round(1).to_string())


if __name__ == "__main__":
    main()
