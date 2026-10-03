# Tunen soil API

This repository contains the frozen-store POC for `POST /soil/layers`. The API
reads precomputed metadata from `docs/poc/store/soil.sqlite` and serves the
referenced artifacts below `/static/`. It does not call SoilGrids or LBEG,
recompute raster values, or refresh the store during a request.

## Local setup and checks

Python 3.9 or newer is required.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

The implementation is organized into the bounded units in
[`docs/implementation-units.md`](docs/implementation-units.md). The store is
an input artifact for this POC; live provider integrations, raster generation,
refresh, and Phase B clipping are deferred.

Start the application from the repository root with:

```sh
.venv/bin/uvicorn soil_api.app:app --reload
```

The P1.1 bootstrap validates `docs/poc/store/` and opens
`soil.sqlite` in SQLite read-only mode. The HTTP routes are added by later
implementation units.
