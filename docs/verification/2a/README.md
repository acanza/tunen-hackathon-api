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

Result: 22 tests passed.

The M2-2A cases verify:

- two fields preserve their IDs and produce independent artifact IDs;
- one provider failure preserves the successful field and returns `partial`;
- total provider failure returns `failed` with no successful data;
- three fields are rejected by the aggregate field limit;
- existing M1 rendering, nodata, PNG transparency, depth handling, and timeout
  checks remain green.

The fixtures are synthetic and do not prove a second real SoilGrids retrieval.
The live multi-field provider check remains pending; it must be run separately
with the recorded M1 provider access and without credentials in the evidence.
