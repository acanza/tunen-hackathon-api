# Validation and delivery

Use these criteria when implementing or reviewing. Report known limitations;
do not treat them as fulfilled criteria. Tests are not needed for a purely
documentation change.

## Functional core

- The API accepts multiple GeoJSON fields and validates geometries, coordinates,
  identifiers, and size limits. Document Polygon/MultiPolygon support.
- There is real integration with SoilGrids and at least one LBEG source, covering
  texture, ph, soc, nfk, and bodenzahl according to verified capabilities. If
  multiple LBEG sources are needed to cover them, incorporate that need into scope.
- The capability matrix explains why a parameter is unavailable from a source;
  it does not require inventing every parameter/source combination.
- Each available layer returns a PNG, bounds, values, statistics, legend, and
  metadata for provenance, unit, depth, and resolution.
- Input errors, missing coverage, missing values, and provider errors are
  distinguished; partial responses preserve valid work.
- Adding an adapter does not require rewriting coordination or existing routes.

## Evidence-based checks

Prioritize small, deterministic fixtures for local logic; separate external
integration tests, whose execution may depend on network access and availability.

| Case | Expected evidence |
| --- | --- |
| Units and depth | Known values verify conversions and aggregations; assumptions are visible. |
| Field with a hole and `nodata` | Exterior and hole are transparent; missing values are excluded from statistics. |
| Axis order and CRS | A reference point/geometry appears within the correct bounds. |
| Raster/PNG correspondence | The same pixels and mask represent the values and legend. |
| Source down or outside coverage | Explicit status and preservation of layers from other sources. |
| Derived values | Cases with zero, one, and multiple sources; incompatible values excluded. |
| Cache and refresh | Valid results are reused and refresh triggers a new query. |
| Excessive request | Documented rejection before disproportionate work begins. |

Do not confuse tests using mocks with evidence that a real provider works.
Record which real integrations were checked and which remain pending.

## Functionality beyond the core

When included in the assignment: mean or justified aggregation, spread between
sources, separately identified uncertainty, and a programmatic refresh mechanism.
Document formulas, minimum requirements, and behavior with insufficient data.

## Reproducible delivery

- Installation and startup instructions, dependencies, and required configuration.
- OpenAPI contract and an executable request/response example.
- A demonstration field with known provenance and coverage.
- A summary of checks performed and their actual results.
- Limitations concerning availability, depth, resolution, proxies, and licenses.
- A short list of pending work; do not declare the MVP complete if a requirement
  is missing.
