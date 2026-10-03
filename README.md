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

The internal M1/M2 service accepts bounded GeoJSON `Polygon` or `MultiPolygon`
fields, with a required unique `id`, and returns SoilGrids clay layers at
0–30 cm through `SoilLayerService.create_layer` or the isolated multi-field
`create_layers` coordinator. Each field keeps its own status and PNG/JSON
artifacts; a mixed request returns a partial batch instead of discarding valid
layers. Provider access requires network access to SoilGrids. Public FastAPI
routes, additional parameters, and cache reuse belong to later units.
