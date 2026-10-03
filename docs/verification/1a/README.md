# Unit 1A — Minimal domain contract and validation

Status: **complete**. Acceptance date: 2026-10-03 (Europe/Madrid).

Dependencies and feasibility evidence: unit 0A is complete; its accepted live
record verifies SoilGrids clay for the reference field and 0–30 cm inputs.

Implemented scope: strict typed internal request, result, and error models for
one identified GeoJSON field, SoilGrids clay, and fixed 0–30 cm depth. `Polygon`
and `MultiPolygon` are supported. Geometry coordinates use longitude/latitude.
Validation covers ring structure, coordinate ranges, Shapely validity, field
count, required identifier, area, vertices, estimated pixels, parameter, source,
depth, result payload consistency, and `[west, south, east, north]` ordering.

Explicit exclusions: FastAPI routes, provider calls, raster processing,
rendering, storage, additional fields, parameters, and sources.

Limits and runtime budgets:

| Limit | Value |
| --- | ---: |
| Fields | exactly 1 |
| Field area | 1,000 ha |
| Geometry vertices | 5,000 |
| Output pixels | 4,096 |
| Provider calls | 8 |
| Concurrency | 1 |
| Retry attempts | 2 |
| Connect timeout | 10 s |
| Provider request timeout | 45 s |
| Local processing timeout | 30 s |

Grid rows are north-to-south and columns west-to-east. Missing values are JSON
`null`, never zero. `available`, `unsupported`, `outside_coverage`, `no_data`,
and `failed` are distinct result statuses. Available results require both PNG
and JSON-grid references; every other status requires a structured error and
cannot carry layer data.

The bounds and grid-orientation contract is represented without ambiguous nested
coordinate ordering:

```json
{
  "bounds": {"west": 11.0, "south": 52.0, "east": 12.0, "north": 53.0},
  "row_order": "north_to_south",
  "column_order": "west_to_east",
  "null_value": null
}
```

Deterministic checks:

- Command: `.venv/bin/python -m unittest discover -s tests -v`.
- Expected: request validation, limit boundaries, result invariants, and the
  earlier 0A regressions pass.
- Actual: 15 tests passed on 2026-10-03. Tests cover `Polygon`, `MultiPolygon`,
  invalid and unclosed geometries, invalid coordinates, missing/invalid IDs,
  the single-field policy (therefore duplicate IDs cannot enter the bounded
  request), unsupported parameter/source, area, vertex and pixel limits,
  bounds order, explicit failures, and rejection of empty success.
- Compilation check: `PYTHONPYCACHEPREFIX=/tmp/tunen-python-cache
  .venv/bin/python -m compileall -q soil_api tests scripts`; exit 0.
- Evidence: the historical domain-model test suite (removed when the project
  moved to the frozen-store POC).
  and the executable contract in
  [`soil_api/domain/models.py`](../../../soil_api/domain/models.py).

Live checks: not applicable to 1A; provider integration belongs to 1B. Unit 0A
live evidence is reused only as the dependency and does not prove 1A behavior.

Regression checks: all three existing unit 0A deterministic tests pass in the
same suite. The first combined test/compile invocation encountered a sandbox-only
Python bytecode-cache permission error after all 15 tests had passed; directing
the cache to `/tmp` produced exit 0. This was not a source or test failure.

Pending checks / blockers: none for 1A. Real provider access, timeout behavior,
clipping, statistics, PNG/JSON agreement, and artifact registration remain
required for 1B and are not claimed here.

Acceptance decision: complete. The typed contract, documented workload budgets,
startup instructions, boundary rejection, coordinate order, grid orientation,
null representation, and distinct failure outcomes satisfy the 1A closure gate.
M1 remains incomplete until unit 1B passes its own verification.
