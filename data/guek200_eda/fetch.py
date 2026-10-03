# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pandas", "geopandas", "shapely", "pyproj"]
# ///
"""Pull BGR GÜK200 (surface geology 1:200k) for the LuF Seggerde farm fields.

Run from this folder:  uv run fetch.py            (cached raw files are reused)
                       uv run fetch.py --force    (re-download everything)

Unlike BÜK200, the GÜK200 service returns polygon geometry, so the field overlay is an exact
intersection, not point sampling.

Outputs:
  raw/service.json, raw/L4_units_on_farm.geojson   untouched responses
  guek200_units.geojson   geology polygons touching the farm, clipped to the farm bbox
  guek200_fields.csv      plotId x unit with area (ha) and share of the field
  guek200_dominant.csv    one row per field: dominant unit, its share, number of units
"""
import json, sys, time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

BASE = "https://services.bgr.de/arcgis/rest/services/geologie/guek200/MapServer"
HERE = Path(__file__).parent
RAW = HERE / "raw"
FIELDS_SRC = HERE.parent.parent / "LuF-Seggerde-Dev-fields.geojson"
FORCE = "--force" in sys.argv
UA = {"User-Agent": "tunen-hackathon-eda/0.1"}
WORK_CRS = "EPSG:25832"
LAYER = 4  # "GÜK200 - Flächen" (layers 2/3 are ice margins and line features)
KEEP = ["OBJECTID", "Kuerzel", "T1_MatBez", "T1_GenTxt", "T1_PethTxt", "T1_System", "T1_Serie",
        "T1_Stufe", "T1_UStufe", "T2_Kuerzel", "T2_GenTxt", "T2_PethTxt", "T1_Blattnu", "T1_Blattna"]


def get(url, params=None, timeout=60, tries=4):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=UA)
            if r.status_code == 200:
                return r
            print("  http", r.status_code, url[:80], flush=True)
        except requests.RequestException as e:
            print("  err", e.__class__.__name__, url[:80], flush=True)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"gave up: {url}")


def cached(path: Path, fetch):
    if FORCE or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fetch())
    return path.read_bytes()


def load_fields():
    g = gpd.read_file(FIELDS_SRC)
    g["geometry"] = g.geometry.make_valid()
    return g[~g.isArchived].reset_index(drop=True)[["plotId", "fieldName", "area", "geometry"]]


def main():
    fields = load_fields()
    w, s, e, n = fields.total_bounds
    cached(RAW / "service.json", lambda: get(BASE, {"f": "json"}).content)
    body = cached(RAW / f"L{LAYER}_units_on_farm.geojson", lambda: get(f"{BASE}/{LAYER}/query", dict(
        geometry=f"{w},{s},{e},{n}", geometryType="esriGeometryEnvelope", inSR=4326, outSR=4326,
        spatialRel="esriSpatialRelIntersects", outFields="*", returnGeometry="true", f="geojson")).content)
    js = json.loads(body)
    assert not js.get("exceededTransferLimit"), "paginate: more units than maxRecordCount"
    units = gpd.GeoDataFrame.from_features(js["features"], crs=4326)
    units = units[KEEP + ["geometry"]].replace({" ": None})
    units.clip((w, s, e, n)).to_file(HERE / "guek200_units.geojson", driver="GeoJSON")

    f_u, u_u = fields.to_crs(WORK_CRS), units.to_crs(WORK_CRS)
    ov = gpd.overlay(f_u, u_u, how="intersection", keep_geom_type=True)
    ov["area_ha"] = ov.area / 1e4
    ov = ov.groupby(["plotId", "fieldName", "Kuerzel", "T1_GenTxt", "T1_PethTxt", "T1_UStufe"],
                    dropna=False, as_index=False).area_ha.sum()
    ov["share"] = ov.area_ha / ov.groupby("plotId").area_ha.transform("sum")
    ov = ov.sort_values(["fieldName", "share"], ascending=[True, False])
    ov.round({"area_ha": 4, "share": 4}).to_csv(HERE / "guek200_fields.csv", index=False)

    dom = ov.groupby("plotId").head(1).merge(
        ov.groupby("plotId").size().rename("n_units"), on="plotId")
    covered = ov.groupby("plotId").area_ha.sum() / (f_u.set_index("plotId").area / 1e4)
    dom["covered_share"] = dom.plotId.map(covered)
    dom.round({"area_ha": 4, "share": 4, "covered_share": 4}).to_csv(HERE / "guek200_dominant.csv", index=False)

    print(f"guek200: {len(units)} polygons, {units.Kuerzel.nunique()} units on farm; "
          f"{dom.plotId.nunique()}/{len(fields)} fields covered, {(dom.n_units > 1).sum()} with >1 unit")
    print((ov.groupby(["Kuerzel", "T1_GenTxt"], dropna=False).area_ha.sum().sort_values(ascending=False)
           .round(1).to_string()))


if __name__ == "__main__":
    main()
