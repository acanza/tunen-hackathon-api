# /// script
# requires-python = ">=3.11"
# dependencies = ["pyproj", "shapely"]
# ///
"""Bodenschätzung class symbols for the Sachsen-Anhalt side of the farm, from the LAGB open soil data WFS.

    uv run data/seggerde/lagb/fetch_lagb.py      # from the repo root

Service: LAGB_Bodendaten_B1_OpenData (Landesamt für Geologie und Bergwesen Sachsen-Anhalt), open data, no fees.
Layers: Bodenart_Standardklassenzeichen (Klassenzeichen per Bodenschätzung polygon, 1:10 000; no Bodenzahl) and
nutzbare_Feldkapazität__KLZ_BS_ (topsoil FK / nFK in Vol.-% derived from the Klassenzeichen).
Output (EPSG:4326 GeoJSON, as returned): raw/klassenzeichen.geojson, raw/nfk_klz.geojson.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import transform, unary_union

HERE = Path(__file__).resolve().parent
FIELDS = HERE.parent / "clean" / "fields_clean.geojson"
URL = "https://www.geodatenportal.sachsen-anhalt.de/arcgis/services/LAGB/LAGB_Bodendaten_B1_OpenData/MapServer/WFSServer"
LAYERS = {"klassenzeichen": "Bodenart_Standardklassenzeichen", "nfk_klz": "nutzbare_Feldkapazität__KLZ_BS_"}


def main():
    to_utm = Transformer.from_crs(4326, 25832, always_xy=True).transform
    fc = json.loads(FIELDS.read_text())
    farm = unary_union([transform(to_utm, shape(f["geometry"])) for f in fc["features"]])
    minx, miny, maxx, maxy = farm.buffer(100).bounds
    (HERE / "raw").mkdir(exist_ok=True)
    for name, layer in LAYERS.items():
        q = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
             "TYPENAMES": f"LAGB_Bodendaten_B1_OpenData:{layer}",
             "BBOX": f"{minx:.0f},{miny:.0f},{maxx:.0f},{maxy:.0f},urn:ogc:def:crs:EPSG::25832", "OUTPUTFORMAT": "GEOJSON"}
        with urllib.request.urlopen(URL + "?" + urllib.parse.urlencode(q), timeout=300) as r:
            data = json.load(r)
        (HERE / "raw" / f"{name}.geojson").write_text(json.dumps(data, ensure_ascii=False))
        print(f"{name}: {len(data['features'])} features")


if __name__ == "__main__":
    main()
