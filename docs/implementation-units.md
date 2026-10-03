# Verifiable POC implementation units

Date: 2026-10-03

This document defines the smallest implementation units for the frozen-store
POC in [`docs/poc/API_BRIEF.md`](poc/API_BRIEF.md). It replaces the former M0–M5
unit list for this assignment. Work outside these units belongs to the deferred
backlog in [`docs/implementation-plan.md`](implementation-plan.md).

## General rules

- Use the existing precomputed store; do not call external services or
  recompute soil data during a request.
- Keep the SQLite database read-only.
- Preserve every requested parameter/source pair in the response.
- Distinguish `not_applicable`, `unavailable`, `partial`, and successful
  results with their documented reasons.
- Use deterministic contract fixtures from `poc/samples/`.
- Do not claim Phase B or live-provider support from tests for Phase A.

## P1 — Application bootstrap and contract models

P1 is split into four units. Each unit should be implementable and testable
without also implementing an HTTP endpoint.

### P1.1 — Application package, settings, and read-only SQLite connection

**Dependencies:** None.

**Scope:** Create the FastAPI application object, store-root configuration, and
a connection factory that opens `poc/store/soil.sqlite` in read-only mode.
Do not add request models or route handlers.

**Verification:** The application imports, the configured store resolves inside
the repository, a read-only connection can query `sqlite_master`, and an
attempted write fails.

### P1.2 — Store metadata query functions

**Dependencies:** P1.1.

**Scope:** Add typed query functions for `runs`, `source_parameters`,
`colormaps`, `fields`, `field_layers`, and `coverage_areas`. Keep SQL and row
conversion outside route handlers.

**Verification:** Queries return the current run, supported pairs, colour maps,
field records, layer records, and farm coverage using the frozen store. No
query writes or accepts a client-provided path.

### P1.3 — GeoJSON request validation and request models

**Dependencies:** P1.1.

**Scope:** Define the request-side Pydantic models for the API brief's
FeatureCollection, feature identifiers, Polygon/MultiPolygon geometry,
optional `parameters`, optional `sources`, and the 200-feature limit. Do not
assemble a response.

**Verification:** Valid sample input is accepted; omitted filters are
represented as defaults to be expanded later; malformed/unsupported GeoJSON,
unknown values, and more than 200 features produce the documented errors
without store or file access.

### P1.4 — Response and layer models

**Dependencies:** P1.1.

**Scope:** Define typed response models for run metadata, field matching,
bounds, layer statuses/reasons, statistics, colormaps, confidence, provenance,
and artifact URLs. Models must preserve `null` values and the API brief's JSON
names.

**Verification:** A fixture response validates and serializes to the sample
shape without recomputing or normalizing stored values.

## P2 — Matching and layer response assembly

P2 is split so field selection, coverage classification, and response mapping
can be verified independently of endpoint wiring.

### P2.1 — Requested parameter/source matrix expansion

**Dependencies:** P1.2, P1.3, P1.4.

**Scope:** Expand omitted filters to the store-supported values and produce a
stable ordered list of requested parameter/source pairs. Mark pairs absent
from `source_parameters` as `not_applicable`.

**Verification:** Every requested pair is emitted exactly once, including
unsupported pairs with `source_does_not_provide_parameter`.

### P2.2 — `plotId` and geometry field matching

**Dependencies:** P1.2, P1.3.

**Scope:** Implement matching precedence for `properties.plotId`, exact
geometry hash, and documented IoU matching. Return only a match record; do not
build layers.

**Verification:** Known `plotId` wins over geometry, geometry matching works
without `plotId`, and unmatched input is explicitly reported.

### P2.3 — Coverage classification and match metadata

**Dependencies:** P2.2, P1.2.

**Scope:** Classify unmatched geometries as known farm coverage with Phase B
unavailable or outside coverage. Produce `match`, `matched_plot_id`,
`field_name`, and documented bounds in the required order.

**Verification:** Known fields, Phase B polygons, and outside polygons receive
the correct classification without fabricated layer values.

### P2.4 — Stored layer metadata and URL mapping

**Dependencies:** P1.2, P1.4.

**Scope:** Convert one `field_layers` row plus its colormap into one response
layer. Parse stored statistics, confidence, and provenance; generate only
run-relative `/static/` URLs.

**Verification:** Available, partial, unavailable, and stored missing-data
rows map to their documented status/reason/unit/metadata. Missing values remain
`null`.

### P2.5 — `POST /soil/layers` orchestration

**Dependencies:** P2.1, P2.3, P2.4.

**Scope:** Add the route that validates the request, reads the current run,
matches every feature, creates one layer entry per requested pair, and returns
the complete response. It must not call providers or write the store.

**Verification:** The sample request returns one response field per input
feature and the exact expected top-level and nested shape.

## P3 — Static artifact serving

P3 is split between path safety and HTTP delivery.

### P3.1 — Safe artifact path resolution

**Dependencies:** P1.1.

**Scope:** Implement a resolver that accepts only a store-relative path and
returns a file inside `poc/store/`. Reject traversal, absolute paths, and
missing files.

**Verification:** Valid PNG, confidence PNG, and GeoTIFF paths resolve;
traversal and absolute-path attempts cannot escape the store.

### P3.2 — Static artifact route and immutable headers

**Dependencies:** P3.1.

**Scope:** Mount `/static/` using the safe resolver, return the correct media
types, and set
`Cache-Control: public, max-age=31536000, immutable`.

**Verification:** Every available sample URL retrieves its file; missing files
return not-found; serving does not mutate the database or artifacts.

## P4 — Contract and acceptance verification

P4 contains only regression and acceptance evidence; it must not introduce new
runtime behavior.

### P4.1 — Exact sample request/response regression

**Dependencies:** P2.5, P3.2.

**Scope:** Compare the sample request with the reference response, allowing
only key-order differences and the documented float tolerance.

**Verification:** The exact contract passes and returned artifact URLs are
retrievable.

### P4.2 — Matching, status, and missing-value regressions

**Dependencies:** P2.5.

**Scope:** Cover western, eastern, sliver, and outside-coverage examples,
including all requested combinations and `null` values.

**Verification:** LBEG coverage, unavailable yield potential, outside coverage,
and `not_applicable` statuses remain explicit.

### P4.3 — Static safety and read-only store regressions

**Dependencies:** P3.2.

**Scope:** Test content types, immutable caching, missing files, traversal
protection, and the absence of database/artifact mutation.

**Verification:** All static safety criteria pass.

### P4.4 — No-network verification and startup documentation

**Dependencies:** P4.1, P4.2, P4.3.

**Scope:** Add a network-disabled request test and document the exact startup
and verification commands.

**Verification:** The sample request completes without an outbound request and
the documented commands reproduce the acceptance results.

## Deferred units

The following are intentionally not implementation units for this POC:

- clipping new polygons from regional rasters;
- geometry-hash result caching;
- live SoilGrids or LBEG adapters;
- refresh, idempotency, immutable analysis resources, or background jobs;
- derived aggregation, source spread, or new uncertainty calculations;
- frontend UI, deployment, Docker, and remote storage.

They may be planned separately only if the user authorizes the corresponding
scope and supplies acceptance evidence for the new behavior.
