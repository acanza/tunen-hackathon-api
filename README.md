# Tunen soil API

The repository currently contains the verified M0 feasibility probe and the M1
unit 1A internal domain contract. It does not expose an HTTP API yet.

## Local setup and checks

Python 3.9 or newer is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-feasibility.txt -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

The public FastAPI routes, SoilGrids runtime adapter, clipping, rendering, and
artifact storage belong to later units. The M1 contract currently accepts one
GeoJSON `Polygon` or `MultiPolygon` field, with a required `id`, for SoilGrids
clay at 0–30 cm.

