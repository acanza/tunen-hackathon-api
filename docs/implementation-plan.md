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
| P1.1 | Application package, settings, and read-only SQLite connection | None |
| P1.2 | Store metadata query functions | P1.1 |
| P1.3 | GeoJSON request validation and request models | P1.1 |
| P1.4 | Response and layer models | P1.1 |
| P2.1 | Requested parameter/source matrix expansion | P1.2, P1.3, P1.4 |
| P2.2 | `plotId` and geometry field matching | P1.2, P1.3 |
| P2.3 | Coverage classification and match metadata | P2.2 |
| P2.4 | Stored layer metadata and URL mapping | P1.2, P1.4 |
| P2.5 | `POST /soil/layers` orchestration | P2.1, P2.3, P2.4 |
| P3.1 | Safe artifact path resolution | P1.1 |
| P3.2 | Static artifact route and immutable headers | P3.1 |
| P4.1 | Exact sample request/response regression | P2.5, P3.2 |
| P4.2 | Matching, status, and missing-value regressions | P2.5 |
| P4.3 | Static safety and read-only store regressions | P3.2 |
| P4.4 | No-network verification and startup documentation | P4.1, P4.2, P4.3 |

### Delivery status

| Unit | Status | Evidence |
| --- | --- | --- |
| P1.1 | Approved | Validated on 2026-10-03: `soil_api.app` imports; settings resolve the repository store and reject an external root; `soil_api.database` queries `sqlite_master`, rejects writes with SQLite read-only mode, and closes connections; no `/soil/*` routes are registered. Startup command is documented in `README.md`. |
| P1.2 | Approved | Validated on 2026-10-03: `soil_api.store` returns the current run, all supported source/parameter pairs, colormaps, field records by plot ID or geometry hash, field layer metadata, and farm coverage from the frozen SQLite store; JSON metadata is parsed into typed records and the module performs no writes or client-path access. |
| P1.3 | Approved | Validated on 2026-10-03: `soil_api.models` accepts the sample FeatureCollection, validates Polygon/MultiPolygon GeoJSON in EPSG:4326 longitude/latitude order, rejects unsupported types and filters, duplicate filters, malformed geometries, and more than 200 features without store or file access. |
| P1.4 | Approved | Validated on 2026-10-03: `soil_api.models` validates the sample response with typed run, field, layer, status, match, confidence, and metadata models; preserves stored `null` values and round-trips `poc/samples/response.json` exactly, including status-specific optional fields. |
| P2.1 | Approved | Validated on 2026-10-03: `soil_api.matrix.expand_requested_layer_pairs` expands omitted filters from the frozen `source_parameters` order, preserves explicit filter order, emits the complete parameter-major Cartesian matrix exactly once, and marks unsupported pairs as `not_applicable` with `source_does_not_provide_parameter`. |
| P2.2 | Approved | Validated on 2026-10-03: `soil_api.matching.match_feature` applies plot ID precedence, store-compatible geometry hashes, and best IoU matching at the 0.95 threshold; known IDs with materially different geometry are reported as `plot_id_geometry_differs`, and unmatched features return an explicit empty match record. |
| P2.3 | Approved | Validated on 2026-10-03: `soil_api.matching.classify_field_match` preserves known-field metadata and stored bounds, classifies unmatched polygons covered by `farm_raster_extent` as `clipped` with documented latitude/longitude bounds, and classifies external polygons as `outside_coverage_area` with null bounds. |
| P2.4 | Approved | Validated on 2026-10-03: `soil_api.layers.map_field_layer` maps all 696 stored layers with status-specific metadata, colormaps, statistics, provenance, confidence artifact URLs, and run-relative static URLs; stored paths are rejected if absolute or traversing outside the store-relative namespace. |
| P2.5 | Approved | Validated on 2026-10-03: `POST /soil/layers` validates requests, reads the current run read-only, expands every requested pair, applies matching and coverage classification, maps stored layers, preserves the exact sample response, returns 413 above 200 features, and returns 422 for unknown filters without provider or network calls. |
| P3.1 | Approved | Validated on 2026-10-03: `soil_api.artifacts.resolve_store_artifact` resolves existing store-relative files, rejects absolute paths, traversal, backslashes, NUL bytes, and missing files, and confirms the resolved path remains inside the configured store after symlink resolution. |
| P3.2 | Approved | Validated on 2026-10-03: `GET /static/{path}` serves all 32 unique sample PNG/GeoTIFF artifacts with correct media types and `Cache-Control: public, max-age=31536000, immutable`; missing, traversal, unsupported-extension, and database paths return 404. |
| P4.1 | Approved | Validated on 2026-10-03: `tests.test_contract` posts `poc/samples/request.json`, compares the complete JSON response with `poc/samples/response.json`, and retrieves every referenced PNG/GeoTIFF URL successfully. |
| P4.2 | Approved | Validated on 2026-10-03: `tests.test_matching_statuses` verifies the complete requested matrix, western LBEG availability, eastern missing coverage, sliver yield unavailability and fallback stats, outside-coverage behavior, and a real stored partial layer without fabricated values or URLs. |

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
