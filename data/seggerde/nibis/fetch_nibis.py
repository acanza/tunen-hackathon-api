# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "numpy", "pillow", "geopandas", "pyproj", "pandas"]
# ///
"""Does LBEG NIBIS (BK50 L816, Bodenschaetzung L849) cover any Seggerde field?

The NIBIS server has a server-wide concurrent-request limit. When it is hit, it answers
HTTP 200 with a ServiceExceptionReport containing "Error 503.2 - Concurrent request limit
exceeded" (not an HTTP error), or requests hang. So: strictly one request at a time, long
timeouts, back off on 503.2, and stop after too many consecutive failures.

Step 1: one GetMap image per layer over the farm (transparent pixels = no polygons there).
Step 2: GetFeatureInfo (10 m box, EPSG:25832) at the representative point of each field
        that has non-transparent pixels; all fields if the image step never succeeds.
Run from this folder: uv run fetch_nibis.py
"""
import io, json, time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests
from PIL import Image
from pyproj import Transformer

HERE = Path(__file__).parent
RAW = HERE / "raw"
URL = "https://nibis.lbeg.de/net3/public/ogc.ashx?PkgId=24"
LAYERS = ("L816", "L849")
BUSY = "503.2"
W, H = 728, 894  # same pixel grid as the Sentinel-2 10 m raster, in EPSG:25832
log = []


def call(params, timeout=60, tries=6, wait=120):
    """One request with backoff. Returns (bytes, content_type) or (None, reason)."""
    for i in range(tries):
        t0 = time.time()
        try:
            r = requests.get(URL, params=params, timeout=timeout)
            dt = time.time() - t0
            busy = BUSY in r.text[:2000] if "xml" in r.headers.get("Content-Type", "") else False
            log.append(dict(t=time.strftime("%H:%M:%S"), req=params["REQUEST"], layer=params["LAYERS"],
                            status=r.status_code, busy=busy, seconds=round(dt, 1)))
            if r.status_code == 200 and not busy:
                return r.content, r.headers.get("Content-Type", "")
            reason = "busy (503.2)" if busy else f"http {r.status_code}"
        except requests.RequestException as e:
            reason = e.__class__.__name__
            log.append(dict(t=time.strftime("%H:%M:%S"), req=params["REQUEST"], layer=params["LAYERS"],
                            status=None, busy=None, seconds=round(time.time() - t0, 1), error=reason))
        print(f"  {params['REQUEST']} {params['LAYERS']}: {reason}, retry in {wait * (i + 1)}s", flush=True)
        time.sleep(wait * (i + 1))
    return None, reason


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    fields = gpd.read_file(HERE.parent / "clean" / "fields_clean.geojson")
    f25 = fields.to_crs(25832)
    x0, y0, x1, y1 = (float(v) for v in (HERE / "bbox_25832.txt").read_text().split(","))
    tr = Transformer.from_crs(4326, 25832, always_xy=True)

    # Step 1: GetMap
    coverage = {}
    for layer in LAYERS:
        body, ctype = call(dict(SERVICE="WMS", VERSION="1.3.0", REQUEST="GetMap", LAYERS=layer, STYLES="",
                                CRS="EPSG:25832", BBOX=f"{x0},{y0},{x1},{y1}", WIDTH=W, HEIGHT=H,
                                FORMAT="image/png", TRANSPARENT="TRUE"))
        if body is None or not ctype.startswith("image"):
            print(f"GetMap {layer} failed: {ctype}")
            continue
        (RAW / f"getmap_{layer}.png").write_bytes(body)
        alpha = np.array(Image.open(io.BytesIO(body)).convert("RGBA"))[..., 3]
        coverage[layer] = alpha
        print(f"GetMap {layer}: {np.mean(alpha > 0):.3%} of the farm bbox has drawn pixels", flush=True)
        time.sleep(5)

    # Which fields have any drawn pixel under them?
    def drawn_share(alpha, geom):
        minx, miny, maxx, maxy = geom.bounds
        c0, c1 = int((minx - x0) / (x1 - x0) * W), int(np.ceil((maxx - x0) / (x1 - x0) * W))
        r0, r1 = int((y1 - maxy) / (y1 - y0) * H), int(np.ceil((y1 - miny) / (y1 - y0) * H))
        sub = alpha[max(r0, 0):r1, max(c0, 0):c1]
        return float(np.mean(sub > 0)) if sub.size else 0.0  # bbox-based, a rough screen

    rows = []
    for i, f in fields.iterrows():
        row = dict(plotId=f.plotId, fieldName=f.fieldName)
        for layer in LAYERS:
            row[f"{layer}_drawn_share_bbox"] = drawn_share(coverage[layer], f25.geometry[i]) if layer in coverage else None
        rows.append(row)
    res = pd.DataFrame(rows)

    # Step 2: GetFeatureInfo where the image shows something (or everywhere if no image)
    for layer in LAYERS:
        col = f"{layer}_drawn_share_bbox"
        todo = res.index if layer not in coverage else res.index[res[col] > 0]
        print(f"GetFeatureInfo {layer}: {len(todo)} fields to query", flush=True)
        fails = 0
        for i in todo:
            f = fields.loc[i]
            x, y = tr.transform(f.rep_lon, f.rep_lat)
            body, ctype = call(dict(SERVICE="WMS", VERSION="1.3.0", REQUEST="GetFeatureInfo", LAYERS=layer,
                                    QUERY_LAYERS=layer, STYLES="", CRS="EPSG:25832",
                                    BBOX=f"{x-5:.2f},{y-5:.2f},{x+5:.2f},{y+5:.2f}", WIDTH=101, HEIGHT=101,
                                    I=50, J=50, INFO_FORMAT="application/geo+json", FEATURE_COUNT=5),
                               tries=3, wait=60)
            if body is None:
                fails += 1
                res.loc[i, f"{layer}_status"] = "failed"
                if fails >= 3:
                    print(f"  {layer}: 3 consecutive failures, stopping this layer", flush=True)
                    break
                continue
            fails = 0
            (RAW / f"gfi_{layer}_{f.plotId}.json").write_bytes(body)
            feats = json.loads(body).get("features", [])
            res.loc[i, f"{layer}_status"] = "feature" if feats else "empty"
            if feats:
                p = feats[0]["properties"]
                for k in ("BL_NAME", "BOTYP_KLARTEXT", "NUTZUNG", "NFKWE", "GWS", "BODENZ", "ACKERZ", "KLASSENZEICHEN"):
                    if k in p:
                        res.loc[i, f"{layer}_{k}"] = p[k]
            time.sleep(2)
    res.to_csv(HERE / "nibis_fields.csv", index=False)
    pd.DataFrame(log).to_csv(HERE / "request_log.csv", index=False)
    print(res.filter(like="_status").apply(lambda s: s.value_counts()).to_string())


if __name__ == "__main__":
    main()
