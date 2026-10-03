# Tunen soil API

The repository currently contains the verified M0 feasibility probe and the
complete M1 single-field SoilGrids clay integration. It does not expose an HTTP
API yet; public routes belong to M5.

## Local setup and checks

Python 3.9 or newer is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-feasibility.txt -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

The M1 service accepts one GeoJSON `Polygon` or `MultiPolygon` field, with a
required `id`, and returns a real SoilGrids clay layer at 0–30 cm through
`SoilLayerService.create_layer`. It stores PNG and JSON artifacts locally.
Provider access requires network access to SoilGrids. Public FastAPI routes,
additional parameters, multiple fields, and cache reuse belong to later units.
