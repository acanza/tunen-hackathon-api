# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "pyproj", "pandas", "shapely"]
# ///
"""
Pull LBEG NIBIS soil data (BK50 + Bodenschätzung) for fixed test sites via
WMS GetFeatureInfo, keep raw responses, and flatten them to a long CSV.

Usage (from this folder):
    uv run fetch.py              # fetch everything (raw/) + flatten (nibis_points_long.csv)
    uv run fetch.py --flatten    # only rebuild the CSV from raw/
    uv run fetch.py --legends    # also download legend PNGs for key layers (raw/legends/)

Polite: sequential requests, sleep between calls, timeout + retries.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests
from pyproj import Transformer
from shapely.geometry import Point, shape

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
CSV_OUT = HERE / "nibis_points_long.csv"
MANIFEST = RAW / "_manifest.json"

# Two endpoints: the soil-map package (PkgId=24) and the separate GLÖZ-5 clay node.
ENDPOINTS = {
    "pkg24": "https://nibis.lbeg.de/net3/public/ogc.ashx?PkgId=24",
    "node2201": "https://nibis.lbeg.de/net3/public/ogc.ashx?NodeId=2201",
}

# (endpoint, layer name, short title)
LAYERS = [
    ("pkg24", "L816", "BK50 - Karte (soil type)"),
    ("pkg24", "L849", "BS5 - Bodenzahl der Bodenschätzung"),
    ("pkg24", "L837", "BK50 - Ertragsfähigkeit"),
    ("pkg24", "L838", "BK50 - Grundwasserstufe"),
    ("pkg24", "L839", "BK50 - nFK des effektiven Wurzelraumes (nFKWe)"),
    ("pkg24", "L821", "BK50 - Pflanzenverfügbares Bodenwasser (1991-2020)"),
    ("pkg24", "L823", "BK50 - Effektive Durchwurzelungstiefe"),
    ("pkg24", "L820", "BK50 - Standortabh. Verdichtungsempfindlichkeit"),
    ("pkg24", "L822", "BK50 - Gefährdung durch Bodenverdichtung"),
    ("pkg24", "L842", "BK50 - Sickerwasserrate (1991-2020)"),
    ("pkg24", "L843", "BK50 - Austauschhäufigkeit Bodenwasser (1991-2020)"),
    ("pkg24", "L841", "BK50 - Bindungsstärke Oberboden Cadmium"),
    ("pkg24", "L1439", "BK50 - Bodenkundl. Feuchtestufe Frühjahrszahl"),
    ("pkg24", "L1440", "BK50 - Bodenkundl. Feuchtestufe Sommerzahl"),
    ("pkg24", "L476", "Sulfatsaure Böden 0-2 m"),
    ("pkg24", "L845", "Kohlenstoffreiche Böden (ohne versiegelt) BHK50KSoVS"),
    ("pkg24", "L846", "Kohlenstoffreiche Böden BHK50"),
    ("pkg24", "L829", "Böden mit hoher natürlicher Bodenfruchtbarkeit"),
    ("pkg24", "L828", "Böden mit besonderen Standorteigenschaften"),
    ("pkg24", "L848", "BK50-BR Bodenregionen"),
    ("pkg24", "L29", "BK50-BGL500 Bodengroßlandschaften"),
    ("pkg24", "L58", "BK50-BL Bodenlandschaften"),
    ("pkg24", "L487", "BUEK500 Bodenübersichtskarte"),
    ("node2201", "L1790", "GLÖZ 5 Tongehalte (25 %)"),
]

LEGEND_LAYERS = ["L837", "L838", "L839", "L821", "L823", "L849", "L820", "L842"]

SITES = [
    ("hildesheimer_boerde", 9.95, 52.22),
    ("hildesheim_edge", 9.95, 52.12),
    ("lueneburger_heide", 10.05, 53.05),
    ("emsland", 7.35, 52.75),
    ("wesermarsch", 8.40, 53.35),
    ("teufelsmoor", 8.90, 53.25),
    ("solling", 9.55, 51.75),
    ("hannover_centre", 9.73, 52.37),
    ("farmland_sg_null", 10.10, 52.18),
    ("hamburg_control", 9.95, 53.55),
]

# Units / meanings for the flattened CSV (only where we are confident; see README).
UNITS = {
    "NFKWE": "mm",
    "WPFL": "mm",
    "WE": "cm (WE=110 -> class \"sehr hoch\" >=11 dm per legend)",
    "BODENZ": "points (0-100)",
    "ACKERZ": "points (0-100+)",
    "AREA": "m2",
    "MHGW": "dm below surface",
    "MNGW": "dm below surface",
    "OST": "m (EPSG:4647, zone-prefixed)",
    "NORD": "m",
    "RECHTS": "m (Gauss-Krüger)",
    "HOCH": "m (Gauss-Krüger)",
    "MBM": "mm/a",
    "BKF": "class (Feuchtestufe)",
    "AH": "1/a (exchange frequency)",
}

HALF = 5.0  # half box size in metres (EPSG:25832). The server's hit tolerance is a few PIXELS:
#             with a 100 m box (~1 m px) neighbouring polygons within ~1.5 m were returned too;
#             a 10 m box (~0.1 m px) returns only the polygon containing the point.
WIDTH = HEIGHT = 101  # odd -> pixel (50,50) is exactly the box centre
SLEEP = 0.4
TIMEOUT = 10  # ~2% of requests hang without answering; a quick retry succeeds
RETRIES = 3

_tr = Transformer.from_crs("EPSG:4326", "EPSG:25832", always_xy=True)


def gfi_params(layer: str, lon: float, lat: float, info_format="application/geo+json") -> dict:
    x, y = _tr.transform(lon, lat)
    return {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": layer,
        "QUERY_LAYERS": layer,
        "STYLES": "",
        "CRS": "EPSG:25832",  # projected, so no lat/lon axis-order trap
        "BBOX": f"{x - HALF:.2f},{y - HALF:.2f},{x + HALF:.2f},{y + HALF:.2f}",
        "WIDTH": WIDTH,
        "HEIGHT": HEIGHT,
        "I": WIDTH // 2,
        "J": HEIGHT // 2,
        "INFO_FORMAT": info_format,  # requests URL-encodes '+' -> %2B (raw '+' breaks)
        "FEATURE_COUNT": 10,
    }


def get(url: str, params: dict | None = None) -> tuple[requests.Response | None, dict, str | None]:
    """Returns (response|None, timing, error). timing = latency of the final attempt,
    total wall time incl. retries/backoff, and number of attempts."""
    err = None
    t_start = time.perf_counter()
    dt = 0.0
    for attempt in range(1, RETRIES + 1):
        t0 = time.perf_counter()
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT,
                             headers={"User-Agent": "tunen-hackathon-eda/0.1 (soil API research)"})
            dt = time.perf_counter() - t0
            if r.status_code == 200:
                return r, {"latency_s": round(dt, 3), "total_s": round(time.perf_counter() - t_start, 3),
                           "attempts": attempt}, None
            err = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            dt = time.perf_counter() - t0
            err = f"attempt {attempt}: {type(e).__name__}"
        print(f"   retry after: {err}", flush=True)
        time.sleep(2 * attempt)
    return None, {"latency_s": round(dt, 3), "total_s": round(time.perf_counter() - t_start, 3),
                  "attempts": RETRIES}, err


def fname(site: str, lon: float, lat: float, layer: str) -> str:
    return f"{site}__{lon:.3f}_{lat:.3f}__{layer}.geojson"


def fetch_all(legends: bool) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    manifest = []
    for site, lon, lat in SITES:
        for ep, layer, title in LAYERS:
            params = gfi_params(layer, lon, lat)
            r, timing, err = get(ENDPOINTS[ep], params)
            path = RAW / fname(site, lon, lat, layer)
            entry = {"site": site, "lon": lon, "lat": lat, "endpoint": ep, "layer": layer,
                     "title": title, "file": path.name, **timing,
                     "error": err, "url": None}
            if r is not None:
                entry["url"] = r.url
                path.write_bytes(r.content)  # untouched raw body
                ctype = r.headers.get("Content-Type", "")
                entry["content_type"] = ctype
                try:
                    entry["n_features"] = len(json.loads(r.content).get("features", []))
                except Exception as e:  # e.g. XML ServiceException
                    entry["n_features"] = None
                    entry["error"] = f"non-JSON body: {e!r}"
            manifest.append(entry)
            print(f"{site:22s} {layer:6s} {entry.get('n_features')!s:>4} feats "
                  f"{timing['latency_s']:5.2f}s x{timing['attempts']} {err or ''}", flush=True)
            time.sleep(SLEEP)
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))

    # Also keep one human-readable text/plain sample per site for the two core layers.
    for site, lon, lat in SITES:
        for layer in ("L816", "L849"):
            r, _, err = get(ENDPOINTS["pkg24"], gfi_params(layer, lon, lat, "text/plain"))
            p = RAW / f"{site}__{lon:.3f}_{lat:.3f}__{layer}.txt"
            p.write_bytes(r.content if r is not None else f"FAILED: {err}".encode())
            time.sleep(SLEEP)

    if legends:
        (RAW / "legends").mkdir(exist_ok=True)
        for layer in LEGEND_LAYERS:
            r, _, err = get(ENDPOINTS["pkg24"], {
                "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetLegendGraphic",
                "LAYER": layer, "FORMAT": "image/png", "STYLE": ""})
            if r is not None:
                (RAW / "legends" / f"{layer}.png").write_bytes(r.content)
            print("legend", layer, err or "ok", flush=True)
            time.sleep(SLEEP)


def flatten() -> pd.DataFrame:
    manifest = json.loads(MANIFEST.read_text())
    rows = []
    for m in manifest:
        base = {"site": m["site"], "lon": m["lon"], "lat": m["lat"],
                "source_layer": m["layer"], "layer_title": m["title"]}
        path = RAW / m["file"]
        if m.get("error") or not path.exists():
            rows.append({**base, "feature_idx": None, "attribute": "_error",
                         "value": m.get("error"), "unit_if_known": None})
            continue
        feats = json.loads(path.read_bytes()).get("features", [])
        rows.append({**base, "feature_idx": None, "attribute": "_feature_count",
                     "value": len(feats), "unit_if_known": None})
        # Geometry comes back in EPSG:4647 (UTM32 with '32' zone prefix on easting).
        x, y = _tr.transform(m["lon"], m["lat"])
        pt = Point(x + 32_000_000, y)
        for i, f in enumerate(feats):
            try:
                inside = shape(f["geometry"]).buffer(0).contains(pt)
            except Exception:
                inside = None
            rows.append({**base, "feature_idx": i, "attribute": "_contains_point",
                         "value": inside, "unit_if_known": None})
            for k, v in (f.get("properties") or {}).items():
                rows.append({**base, "feature_idx": i, "attribute": k, "value": v,
                             "unit_if_known": UNITS.get(k)})
    df = pd.DataFrame(rows)
    df["feature_idx"] = df["feature_idx"].astype("Int64")  # keep ints, blank for meta rows
    df.to_csv(CSV_OUT, index=False)
    print(f"wrote {CSV_OUT} ({len(df)} rows)")
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--flatten", action="store_true", help="only rebuild CSV from raw/")
    ap.add_argument("--legends", action="store_true", help="also fetch legend PNGs")
    a = ap.parse_args()
    if not a.flatten:
        fetch_all(a.legends)
    flatten()
    sys.exit(0)
