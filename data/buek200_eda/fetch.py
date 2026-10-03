# /// script
# requires-python = ">=3.10"
# dependencies = ["requests", "beautifulsoup4"]
# ///
"""Pull BGR BÜK200 point data for the hackathon test sites.

Usage:
    uv run fetch.py            # fetch raw responses into raw/ (skips files that exist)
    uv run fetch.py --force    # re-fetch everything
    uv run fetch.py --flatten  # only rebuild CSVs from raw/ (no network)

Per site it does (sequentially, with sleeps):
  1. query layer 0 (Blattschnitt = sheet index)  -> which of the 55 map sheets contains the point
  2. query the matching sheet layer (2..56)       -> legend unit polygon attributes
  3. identify on all layers (cross-check)         -> same info, alias names, string-formatted values
  4. GET the FISBo profile page (HTML) per legend unit -> horizon data of the reference profile(s)

Outputs:
  raw/                    untouched responses (one file per site x request)
  raw/_fetch_log.json     url, http status, latency per request
  buek200_long.csv        site, lon, lat, layer, attribute, value   (everything, long format)
  buek200_horizons.csv    one row per horizon of each reference profile (parsed from FISBo HTML)
"""
import csv
import html
import json
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE = "https://services.bgr.de/arcgis/rest/services/boden/buek200/MapServer"
HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
UA = {"User-Agent": "tunen-hackathon-soil-eda/0.1 (research; contact via repo)"}
SLEEP = 1.0

SITES = {  # name: (lon, lat)  -- the fixed test sites
    "Hildesheimer Börde (loess)": (9.95, 52.22),
    "Hildesheim edge (SoilGrids null)": (9.95, 52.12),
    "Lüneburger Heide (sand)": (10.05, 53.05),
    "Emsland (sand/peat)": (7.35, 52.75),
    "Wesermarsch (marsh clay)": (8.40, 53.35),
    "Teufelsmoor (bog)": (8.90, 53.25),
    "Solling (upland forest)": (9.55, 51.75),
    "Hannover centre (urban)": (9.73, 52.37),
    "Farmland SoilGrids null": (10.10, 52.18),
    "Hamburg (outside NI)": (9.95, 53.55),
}
EDGE_SITES = {  # extra probes for coverage behaviour (not part of the test set)
    "EDGE Steinhuder Meer (lake)": (9.32, 52.46),
    "EDGE North Sea offshore": (7.50, 54.00),
    "EDGE Netherlands (outside DE)": (6.30, 52.50),
}

HORIZON_COLS = [
    "nr", "horizon_symbol", "top_dm", "bottom_dm", "stratigraphy", "origin",
    "geogenesis", "coarse_fraction", "coarse_content_class", "texture_ka5",
    "humus_class", "carbonate_class", "structure", "bulk_density_class",
    "peat_type", "peat_decomposition", "peat_substance_volume", "acidity_class",
]

LOG = []


def tag(lon, lat):
    return f"{lon:.3f}_{lat:.3f}"


def get(url, params=None, timeout=60, tries=4):
    last = None
    for i in range(tries):
        t0 = time.time()
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=UA)
            dt = round(time.time() - t0, 3)
            LOG.append({"url": r.url, "status": r.status_code, "seconds": dt, "try": i + 1})
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            LOG.append({"url": url, "params": params, "error": repr(e), "try": i + 1})
            last = repr(e)
        time.sleep(3 * (i + 1))
    raise RuntimeError(f"giving up on {url}: {last}")


def point_query(layer_id, lon, lat):
    return {
        "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects", "outFields": "*",
        "returnGeometry": "false", "f": "json",
    }


def save(path, text):
    path.write_text(text, encoding="utf-8")


def fetch(force=False):
    RAW.mkdir(exist_ok=True)
    svc_path = RAW / "service.json"
    if force or not svc_path.exists():
        save(svc_path, get(BASE, {"f": "json"}).text)
        time.sleep(SLEEP)
    svc = json.loads(svc_path.read_text(encoding="utf-8"))
    # "CC3918 HANNOVER" -> layer 17 ; sheet index BLATTNUM is "CC 3918"
    sheet_layer = {l["name"].split()[0]: l["id"] for l in svc["layers"] if re.match(r"CC\d{4} ", l["name"])}

    for name, (lon, lat) in {**SITES, **EDGE_SITES}.items():
        t = tag(lon, lat)
        print(f"--- {name} {t}", flush=True)
        # 1. sheet index
        p = RAW / f"query_L0_sheetindex_{t}.json"
        if force or not p.exists():
            save(p, get(f"{BASE}/0/query", point_query(0, lon, lat)).text)
            time.sleep(SLEEP)
        sheets = [f["attributes"]["BLATTNUM"].replace(" ", "") for f in json.loads(p.read_text())["features"]]
        # 2. sheet layer query
        tkles = []
        for s in sheets:
            lid = sheet_layer.get(s)
            if lid is None:
                print("  no layer for sheet", s)
                continue
            p = RAW / f"query_L{lid}_{s}_{t}.json"
            if force or not p.exists():
                save(p, get(f"{BASE}/{lid}/query", point_query(lid, lon, lat)).text)
                time.sleep(SLEEP)
            for f in json.loads(p.read_text())["features"]:
                tkles.append((f["attributes"]["TKLE_NR"], f["attributes"].get("Profile")))
        # 3. identify (cross-check; all layers)
        p = RAW / f"identify_{t}.json"
        if force or not p.exists():
            d = 0.01
            params = {
                "geometry": f"{lon},{lat}", "geometryType": "esriGeometryPoint", "sr": 4326,
                "layers": "all", "tolerance": 0, "returnGeometry": "false",
                "mapExtent": f"{lon - d},{lat - d},{lon + d},{lat + d}",
                "imageDisplay": "400,400,96", "f": "json",
            }
            save(p, get(f"{BASE}/identify", params).text)
            time.sleep(SLEEP)
        # 4. profile pages
        for tkle, prof_url in tkles:
            if not prof_url:
                print("  no profile url for", tkle)
                continue
            p = RAW / f"profile_TKLE{tkle}_{t}.html"
            if force or not p.exists():
                try:
                    save(p, get(html.unescape(prof_url)).text)  # NB: URL comes with &amp;
                except RuntimeError as e:
                    save(RAW / f"profile_TKLE{tkle}_{t}.FAILED.txt", str(e))
                time.sleep(SLEEP)
        print("  sheets", sheets, "TKLE", [x[0] for x in tkles], flush=True)

    logp = RAW / "_fetch_log.json"
    old = json.loads(logp.read_text()) if logp.exists() and not force else []
    save(logp, json.dumps(old + LOG, indent=1, ensure_ascii=False))


# ---------------------------------------------------------------- parsing
def parse_profile_html(text):
    """Return (unit_header, [profile dicts]) from a FISBo getProfile page."""
    soup = BeautifulSoup(text, "html.parser")
    clean = lambda s: re.sub(r"\s+", " ", s.replace("\xad", "")).strip()
    head = soup.find("tr", class_="legendeneinheit")
    unit = clean(head.get_text(" ")) if head else ""
    profiles = []
    for th in soup.find_all("th", class_="profil"):
        divs = [clean(d.get_text(" ")) for d in th.find_all("div", recursive=False)]
        meta = {"header": " | ".join(divs)}
        for d in divs:
            if d.startswith("Profil:"):
                meta["profile"] = d.split(":", 1)[1].strip()
            elif ":" in d:
                k, v = d.split(":", 1)
                meta[k.strip()] = v.strip()
        table = th.find_parent("tr").find_next_sibling("tr").find("table")
        horizons = []
        for tr in table.find_all("tr", recursive=False):
            if "mouseOver" not in (tr.get("onmouseover") or ""):
                continue
            tds = [td for td in tr.find_all("td", recursive=False) if not td.has_attr("rowspan")]
            vals = [clean(td.get_text(" ")) for td in tds]
            if len(vals) != len(HORIZON_COLS):
                vals = vals + [""] * (len(HORIZON_COLS) - len(vals))
                meta.setdefault("parse_warning", f"unexpected column count {len(tds)}")
            horizons.append(dict(zip(HORIZON_COLS, vals)))
        meta["horizons"] = horizons
        profiles.append(meta)
    return unit, profiles


def flatten():
    long_rows, hz_rows = [], []
    for name, (lon, lat) in {**SITES, **EDGE_SITES}.items():
        t = tag(lon, lat)
        add = lambda layer, attr, val: long_rows.append(
            {"site": name, "lon": lon, "lat": lat, "layer": layer, "attribute": attr,
             "value": "" if val is None else val})
        for p in sorted(RAW.glob(f"query_L*_{t}.json")):
            js = json.loads(p.read_text(encoding="utf-8"))
            layer = p.stem.replace(f"_{t}", "").replace("query_", "")
            if "error" in js:
                add(layer, "ERROR", json.dumps(js["error"], ensure_ascii=False))
            if not js.get("features"):
                add(layer, "n_features", 0)
            for f in js.get("features", []):
                for k, v in f["attributes"].items():
                    if k == "Profile" and v:
                        v = html.unescape(v)
                    add(layer, k, v)
        p = RAW / f"identify_{t}.json"
        if p.exists():
            js = json.loads(p.read_text(encoding="utf-8"))
            for r in js.get("results", []):
                if r["layerId"] in (0, 1):
                    continue  # duplicates of sheet index / raster colour
                for k, v in r["attributes"].items():
                    add(f"identify_L{r['layerId']}", k, v)
        for p in sorted(RAW.glob(f"profile_TKLE*_{t}.*")):
            tk = re.search(r"TKLE(\d+)", p.name).group(1)
            if p.suffix == ".txt":
                add(f"profile_{tk}", "FETCH_FAILED", p.read_text())
                continue
            unit, profiles = parse_profile_html(p.read_text(encoding="utf-8"))
            add(f"profile_{tk}", "unit_header", unit)
            add(f"profile_{tk}", "n_profiles", len(profiles))
            if not profiles:  # e.g. urban cores / water: page says "keine Profildaten hinterlegt"
                txt = re.sub(r"\s+", " ", BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser").get_text(" ")).strip()
                add(f"profile_{tk}", "note", txt)
            for pr in profiles:
                pn = pr.get("profile", "?").split(" ")[0]
                for k, v in pr.items():
                    if k not in ("horizons", "header", "profile"):
                        add(f"profile_{tk}", f"p{pn}.{k}", v)
                for h in pr["horizons"]:
                    for k, v in h.items():
                        if k != "nr":
                            add(f"profile_{tk}", f"p{pn}.h{h['nr']}.{k}", v)
                    hz_rows.append({"site": name, "lon": lon, "lat": lat, "TKLE_NR": tk,
                                    "profile": pr.get("profile", ""),
                                    "soil_unit": pr.get("Bodensystematische Einheit", ""),
                                    "area_share": pr.get("Flächenanteil", ""),
                                    "land_use": pr.get("Landnutzung", ""), **h})
    with open(HERE / "buek200_long.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["site", "lon", "lat", "layer", "attribute", "value"])
        w.writeheader(); w.writerows(long_rows)
    cols = ["site", "lon", "lat", "TKLE_NR", "profile", "soil_unit", "area_share", "land_use"] + HORIZON_COLS
    with open(HERE / "buek200_horizons.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader(); w.writerows(hz_rows)
    print(f"wrote {len(long_rows)} long rows, {len(hz_rows)} horizon rows")


if __name__ == "__main__":
    if "--flatten" not in sys.argv:
        fetch(force="--force" in sys.argv)
    flatten()
