# Tunen Soil API

This project was developed to participate in the **Tunen** track challenge at
the **Madrid Open Vol. 1** hackathon, organized by companies **Tunen Labs, Reversa, and
Talky**.

## What does it do?

This is a proof of concept for a soil-layer API. It receives a GeoJSON
`FeatureCollection` containing the plots or fields to analyze and returns the
soil layers available for each field, parameter, and source combination. The
response includes the status of each result, its metadata, statistics,
provenance, and links to the associated geospatial artifacts.

The current implementation uses a frozen, precomputed run:

- `POST /soil/layers` validates the request, identifies the fields, and
  assembles the response from the available catalog.
- `GET /static/{path}` safely serves the PNG and GeoTIFF artifacts referenced by
  the response.
- Metadata is read from `docs/poc/store/soil.sqlite` in read-only mode.
- No calls to SoilGrids, LBEG, or other external services are made during a
  request, and rasters are not recomputed at request time.

This scope demonstrates the complete contract and workflow without presenting
demonstration data as a production-ready provider integration.

## Stack and architecture

A small, familiar stack was chosen to prioritize an end-to-end working flow:

- **Python 3.9+** as the programming language, because of its ecosystem for
  APIs and geospatial data.
- **FastAPI** to expose the HTTP endpoint and automatically provide OpenAPI
  documentation.
- **Pydantic** to validate the JSON contract and GeoJSON geometries before
  accessing the catalog.
- **Shapely** to validate and compare field geometries.
- **SQLite** as an embedded catalog, which is easy to distribute and sufficient
  for a read-only proof of concept.
- **Uvicorn** as the local ASGI server.

The architecture follows an intentionally simple pipeline:

```text
FastAPI request
  -> Pydantic/GeoJSON validation
  -> read-only SQLite metadata access
  -> field matching and coverage classification
  -> response assembly
  -> safe artifact resolution and static file serving
```

The logic is separated into models and validation, catalog access, geospatial
matching, layer composition, and artifact resolution. This keeps a clear
boundary between the HTTP contract and the precomputed data, without
introducing infrastructure that was not needed for the challenge objective.

## MVP trade-offs

The main constraint was having **only 10 hours** to complete a demonstrable
submission. The most important decisions were:

- **Data preparation across heterogeneous sources.** One of the major
  challenges was extracting data from aggregated sources such as SoilGrids and
  LBEG, cleaning and normalizing their different formats and semantics, and
  storing the resulting metadata and artifacts in a structure that the API
  could consume efficiently and consistently.
- **Reliability and reproducibility over real-time data.** A frozen store and
  precomputed artifacts avoid making the submission dependent on the
  availability, limits, formats, or changes of external services.
- **SQLite over a managed database.** It eliminates setup and makes the demo
  portable, but it does not provide the scalability, concurrency, or
  multi-user operation expected from a production solution.
- **Preprocessing over on-demand computation.** Responses are fast and stable,
  but the system cannot yet recalculate layers for arbitrary geometries or
  automatically refresh provider data.
- **A modular architecture without distributed infrastructure.** The
  responsibilities are separated to provide a clear path toward provider
  adapters and raster processing, while queues, workers, caches, and
  additional services were deliberately left out because they would have
  consumed time without improving the main demonstration.
- **Explicit coverage over fabricated values.** Each combination can report
  `not_applicable`, `unavailable`, or `partial`; when data is missing, the API
  does not manufacture a result to suggest complete coverage.

The result is therefore a **functional, reproducible MVP**, not a production
platform. Natural next steps include live provider integrations, on-demand
raster generation and clipping, refresh mechanisms, scalable storage, and
observability and deployment strategies.

## Getting started

Python 3.9 or newer is required:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Start the application from the repository root:

```sh
.venv/bin/uvicorn soil_api.app:app --reload
```

The implementation is organized into the bounded units described in
[`docs/implementation-units.md`](docs/implementation-units.md). The store is
an input artifact for this POC; provider integrations, raster generation,
refresh, and Phase B clipping are outside the current scope.

## Checks

Contract regression:

```sh
.venv/bin/python -m unittest tests.test_contract
```

Complete POC regression suite:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The suite covers the sample contract, matching and coverage statuses, static
artifact safety, read-only store access, and a request with outbound network
connections blocked.
