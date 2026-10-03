# Soil API POC implementation plan

Date: 2026-10-03

## Decision

The current assignment is a read-only POC over the precomputed store described
in [`docs/poc/API_BRIEF.md`](poc/API_BRIEF.md). The API does not retrieve from
SoilGrids or LBEG, recompute soil data, or refresh the store during a request.
The frozen run `poc-2026-10-03` is the data contract for this delivery.

The previous M0–M5 architecture is retired as an implementation path for this
POC. Its completed feasibility and domain work remains historical evidence, but
it does not create additional POC tasks or public routes.

## POC objective

Implement one small FastAPI application that:

1. Reads metadata from `poc/store/soil.sqlite` in read-only mode.
2. Reads the precomputed PNG, confidence PNG, and GeoTIFF files from
   `poc/store/`.
3. Exposes `POST /soil/layers` for the request and response in the API brief.
4. Serves referenced files below `/static/`.
5. Returns an explicit result for every requested parameter/source pair,
   including `not_applicable`, `unavailable`, and `partial`.
6. Makes no outbound network calls during a request.

## Public POC surface

Only these routes are in scope:

| Route | Purpose |
| --- | --- |
| `POST /soil/layers` | Match submitted fields and return precomputed layers. |
| `GET /static/{path}` | Serve allow-listed files below `poc/store/`. |

The following routes are explicitly out of scope: `/soil/analyses`,
`/soil/fields`, `/soil/runs/current`, `/soil/capabilities`, `/rasters/*`,
`/health`, refresh endpoints, sampling plans, parcel datasheets, management
signals, and artifact indirection endpoints.

## Minimal architecture

```text
FastAPI request
  -> Pydantic validation
  -> read-only SQLite metadata
  -> field matching
  -> response assembly from precomputed metadata and file paths
  -> static file serving
```

No provider adapters, raster processing pipeline, database writes, cache, queue,
background job, or live-service client is needed for this POC.

## Delivery units

The bounded units and their evidence are defined in
[`docs/implementation-units.md`](implementation-units.md).

| Unit | Scope | Depends on |
| --- | --- | --- |
| P1 | Application bootstrap, read-only store access, and request/response models | None |
| P2 | Field matching and `POST /soil/layers` response assembly | P1 |
| P3 | Static artifact serving and safe immutable caching headers | P1 |
| P4 | Contract and acceptance verification | P2, P3 |

## Completion gate

The POC is complete when P1–P4 pass and the exact sample request produces the
sample response, allowing only documented JSON key-order and float-tolerance
normalization. The contract must also demonstrate:

- a western field with available LBEG data;
- an eastern field without LBEG coverage;
- a sliver with unavailable yield potential and fallback statistics;
- a polygon outside the farm coverage area;
- no outbound network calls during request handling.

## Deferred backlog

These items are not dependencies of the POC:

- **B1 — New polygons:** implement the API brief's Phase B clipping of
  `regional_rasters`, including `geom_hash` caching.
- **B2 — Convenience packaging:** add `run_id` selection, an OpenAPI example,
  and a Dockerfile.
- **B3 — Frontend demo:** add the optional Leaflet page.
- **B4 — Live or versioned analysis API:** design a separate contract for live
  providers, refresh, immutable analyses, derived products, or asynchronous
  work. None of those concepts should be mixed into this POC.

Each backlog item requires a new bounded plan and acceptance evidence before
implementation.

## Operational constraints

- Keep the SQLite connection read-only.
- Resolve file paths only under `poc/store/`; never accept arbitrary client
  filesystem paths or provider URLs.
- Preserve the frozen run identifier and data-as-of metadata.
- Return explicit reasons for missing coverage, unsupported pairs, and missing
  data; never turn them into empty success values.
- Keep GeoJSON input in longitude/latitude order and return the documented
  bounds order from the API brief.
