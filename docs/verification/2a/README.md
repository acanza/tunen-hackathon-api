# M2-2A verification: multiple fields and isolated failures

Date: 2026-10-03

## Scope

The internal coordinator now accepts up to two uniquely identified fields for
the existing `clay`/SoilGrids integration. Request-wide budgets are checked
before provider work: two fields may use at most 16 estimated provider calls
and 8,192 estimated output pixels. Processing uses at most two worker threads,
and each field has the configured processing timeout.

Each field is converted to a single-field request for the existing adapter.
The adapter and artifact store are not shared through mutable per-field state.
UUID artifact identifiers therefore remain distinct. A batch is `available`
when all fields succeed, `partial` when at least one succeeds and another
does not, and `failed` when no field succeeds.

## Deterministic evidence

Executed:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Result: 23 tests passed.

The M2-2A cases verify:

- two fields preserve their IDs and produce independent artifact IDs;
- one provider failure preserves the successful field and returns `partial`;
- total provider failure returns `failed` with no successful data;
- `outside_coverage` remains distinct from `no_data`;
- three fields are rejected by the aggregate field limit;
- existing M1 rendering, nodata, PNG transparency, depth handling, and timeout
  checks remain green.

## Live provider evidence

- Date: 2026-10-03, UTC retrievals at
  `2026-10-03T13:53:30.953757+00:00` and
  `2026-10-03T13:53:31.004137+00:00`.
- Request: two distinct Polygon geometries in the verified SoilGrids reference
  coverage.
- Source: SoilGrids WCS clay coverages `clay_0-5cm_mean`,
  `clay_5-15cm_mean`, and `clay_15-30cm_mean`; SoilGrids250m 2.0 / RUN10.
- Outcome: batch `available`; both fields returned `available` results.
- First field: `Hk3aYz9j56wbQD4u3rAC`, 3 × 3 grid, 5 valid pixels.
- Second field: `m2-2a-inset-field`, 1 × 1 grid, 1 valid pixel.
- Each field returned two artifact references and all artifact identifiers were
  distinct. Provenance included retrieval time, source CRS, 250 m source
  resolution, depth intervals, attribution, and license.
- Temporary artifact storage was removed after verification; no provider bytes
  or generated artifacts were committed.

The deterministic fixtures remain the evidence for injected provider failure,
partial results, total failure, missing data, and aggregate limit rejection.
The real LBEG failure-isolation check remains intentionally deferred to unit 2E,
where that adapter becomes available.

Acceptance decision: **complete for the current SoilGrids clay integration**.

The LBEG failure-isolation check remains intentionally deferred to unit 2E,
where that adapter becomes available.
