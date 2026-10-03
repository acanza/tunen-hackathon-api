# POC acceptance criteria

These criteria validate the frozen-store POC described in
[`docs/poc/API_BRIEF.md`](../../../docs/poc/API_BRIEF.md). They do not prove
live provider access or the deferred analysis API.

## Functional contract

- `POST /soil/layers` accepts the documented FeatureCollection request.
- Missing `parameters` or `sources` expands to the supported store matrix.
- Unknown values return `422`; more than 200 features returns `413`.
- Every requested parameter/source pair appears in every field response.
- Available layers return their stored URLs, stats, colormap, confidence, and
  provenance without recomputation.
- Unsupported pairs are `not_applicable` with
  `source_does_not_provide_parameter`.
- Missing coverage, missing data, and Phase B polygons have explicit
  `unavailable` reasons.
- Missing values remain `null`, never zero.

## Matching and coverage

- Known `plotId` matching takes precedence.
- Geometry hash or IoU matching works when no known `plotId` is supplied.
- Geometry differences are reported according to the API brief.
- Western and eastern field behavior preserves the stored LBEG coverage.
- Outside-coverage polygons return `200` with unavailable layers.
- Phase B is not silently implemented by returning fabricated or recomputed
  values.

## Artifacts and safety

- Referenced PNG, confidence PNG, and GeoTIFF files are retrievable below
  `/static/`.
- Static responses have the documented immutable cache header.
- File resolution cannot escape `poc/store/`.
- SQLite is opened read-only and no request writes store data.

## Reproducible verification

- `poc/samples/request.json` produces `poc/samples/response.json`, allowing
  only key-order differences and documented float tolerance.
- The sliver and outside-coverage acceptance examples pass.
- A network-disabled or no-network test demonstrates that request handling
  performs no outbound calls.
- Startup and verification commands are documented.

Provider integration, refresh, asynchronous work, cross-source aggregation,
analysis resources, and frontend products are deferred and must not be reported
as complete based on this POC evidence.
