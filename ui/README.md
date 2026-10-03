# Seggerde soil UI (POC)

React app for `poc/UI_BRIEF.md`, built on the API contract in `poc/API_BRIEF.md` / `poc/samples/`.

```bash
npm install
npm run dev          # http://localhost:5173, mock API (no backend needed)
npm test             # contract + domain tests
```

## Mock vs real API

- **`VITE_API_URL` unset (default):** data comes from `public/mock/` and the dev server serves `../poc/store` at `/static/`.
- **`VITE_API_URL=http://localhost:8000`** (in `.env.local`): `/soil`, `/static` and `/health` are proxied to the API.
  No code changes. Everything goes through `src/api/client.ts`.

Mocks are generated from the store, not hand-written (run from the repo root):

```bash
uv run ui/scripts/export_fixtures.py       # fields, layers per field, meta  (uses assemble_response() from poc/build_store.py)
uv run ui/scripts/make_proposed_mocks.py   # 🔴 proposed shapes for 6 demo fields (sampling plan, signals, crops, …)
```

`npm test` checks that the mock reproduces `poc/samples/response.json` exactly and that every fixture parses with the
contract schema (`src/api/schema.ts`), so contract drift shows up as a test failure.

## Screens

| Route | Screen (UI_BRIEF) |
|---|---|
| `/` | 1. Farm overview: colour by survey coverage or any field statistic (low confidence → grey) |
| `/field/:plotId/maps` | 2. Property maps with layer/source switchers and the masking rule |
| `/field/:plotId/yield` | 3. Relative yield pattern, "your usual yield" → t/ha per zone |
| `/demo/before-after` | 4. Siloed sources → `best` with source mask → disagreement (preview) |
| `/field/:plotId/sheet` | 5. Spec sheet: farmer sentences linked 1:1 to audit rows; print/PDF |
| `/about` | 6. Sources, licences, methods, validation |
| `/field/:plotId/sampling`, `/signals` | 🔴 Sampling plan (GPX/CSV export), signals, crop suitability: mock data, badged "Preview" |

## Masking rule

Low-confidence pixels never show the layer colour. Until the data side ships `masked_png_url`, `src/map/masking.ts`
repaints the server's layer PNG (EPSG:3857). For each PNG pixel it reads the confidence from band 4 of the GeoTIFF
(EPSG:32632). The result lines up pixel for pixel with the other overlays. When a layer has `masked_png_url`,
`SoilLayerOverlay` uses that file instead.

## Open points with the API developer

- `GET /soil/meta` (sources, source_parameters, validation, runs) is needed by the spec sheet and the About page.
  The shape is `public/mock/meta.json`. Until it exists, the HTTP client falls back to the mock.
- `GET /soil/fields` property names are assumed to be `plotId, name, area_ha, state, use_for_stats` (no sample exists).
- The 🔴 endpoints (sampling plan etc.) are still mock-only. `getProposed()` in `client.ts` is where to wire them up.
