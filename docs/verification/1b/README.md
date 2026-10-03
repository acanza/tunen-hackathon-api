# Unit 1B — One complete real layer (historical)

Status: **complete**. Acceptance date: 2026-10-03 (Europe/Madrid).

Dependencies and feasibility evidence: unit 1A is complete and unit 0A
contains accepted live SoilGrids clay evidence for the reference field and its
0–5, 5–15, and 15–30 cm coverages.

Historical implemented scope:

- `SoilGridsAdapter` and single-field coordination through
  `SoilLayerService.create_layer`.
- WCS capabilities and coverage-description checks.
- Bounded SoilGrids requests with 45-second timeouts, two transient retries,
  8 MiB response limits, and a 4,096-pixel raster budget.
- Native-grid clipping using the field geometry, including polygon holes.
- Thickness-weighted clay normalization from g/kg to percent for 0–30 cm.
- `nodata` exclusion and all-nodata failure handling.
- Local immutable PNG and JSON artifact storage and retrieval.
- Statistics, legend, grid orientation, transform, source metadata, and
  provenance in the returned `LayerResult`.
- Explicit provider timeout, provider failure, and processing failure results.

Explicit exclusions: FastAPI routes, multiple fields, parameters other than
clay, sources other than SoilGrids, cache reuse, refresh, and public M5
endpoints.

Decisions and limitations:

- SoilGrids native CRS is retained on the grid; input GeoJSON is transformed
  from EPSG:4326 before clipping.
- Grid rows are north-to-south and columns west-to-east.
- Clay uses `(5*c0_5 + 10*c5_15 + 15*c15_30) / 3000` where inputs are g/kg
  and output is percent. All three depth intervals are required per cell.
- PNG pixels use the same mask as the JSON grid; masked pixels have alpha zero.
- The dataset date is unavailable from provider metadata and remains null.
- The live response is a technical integration demonstration, not a
  parcel-area-weighted statistic.

Deterministic checks:

- Actual: **19 tests passed** on 2026-10-03.
- The source tests and provider implementation were removed when the project
  moved to the frozen-store POC; this document remains historical evidence.
- Checks cover known depth math, axis/orientation metadata, JSON artifact
  retrieval, PNG generation, `nodata` to JSON null, transparent PNG pixels,
  all-nodata handling, and explicit timeout errors.

Live checks:

- Date: 2026-10-03, UTC retrieval at `2026-10-03T13:33:20.582815+00:00`.
- Request: accepted 0A reference field `Hk3aYz9j56wbQD4u3rAC`.
- Source: SoilGrids WCS clay coverages `clay_0-5cm_mean`,
  `clay_5-15cm_mean`, and `clay_15-30cm_mean`; SoilGrids250m 2.0 / RUN10.
- Outcome: available layer, 3 × 3 native grid, 5 valid pixels, range
  1.7266667–2.015 percent, and both PNG and JSON artifacts retrieved
  successfully.
- The temporary artifact directory was removed after verification; no live
  provider bytes were committed.

Pending checks / blockers: no blocker remains for 1B. A public HTTP route,
multi-field behavior, additional parameters, and cache behavior are deferred
to later units.

Acceptance decision: **complete**. The real-provider, artifact, masking,
statistics, provenance, timeout, and deterministic verification gates passed.
M1 was complete after 1A and 1B. It is not an active implementation path for
the frozen-store POC.
