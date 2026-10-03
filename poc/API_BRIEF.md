# API brief: `POST /soil/layers` (POC)

You build the HTTP API. The data side is done for the POC: every pixel, statistic and confidence value is already precomputed in `poc/store/`. The API **reads files and a SQLite DB, and never calls an external service or recomputes soil data during a request.**

The data is frozen as of 2026-10-03 (run `poc-2026-10-03`) and there is no refresh in the POC. Anything that would change it is out of scope.

## What's in the repo

| Path | What it is |
|---|---|
| `poc/store/soil.sqlite` | **The DB you query.** Metadata only; schema in `poc/schema.sql` |
| `poc/store/runs/poc-2026-10-03/fields/<plotId>/` | Per field and layer: `<param>__<source>.tif` (values), `.png` (map overlay), `__conf.png` (low-confidence hatch); for `best` also `__source.png` (which source won where) |
| `poc/store/runs/poc-2026-10-03/regional/` | Farm-wide rasters, one per layer, for clipping polygons that are not known fields (phase B) + `bodenschaetzung_parcels.geojson` |
| `poc/store/runs/poc-2026-10-03/covariates/` | Model inputs (terrain: elevation, slope, wetness index, relative elevation). **Not API layers; ignore them** |
| `poc/UI_BRIEF.md` | What the app will show and the proposed additions it needs (masked PNG, signals, sampling plan, crop suitability) |
| `poc/samples/request.json` | Example request: a west field, an east field, a sliver, a polygon outside the farm |
| `poc/samples/response.json` | **The exact response that request must produce.** Use it as your contract test |
| `poc/build_store.py` | How the store was built (`uv run poc/build_store.py` rebuilds it in ~40 s). `assemble_response()` at the bottom is a reference for the response logic |

The store is ~12 MB, 87 fields, 1,530 files.

## The farm in one paragraph

LuF Seggerde has 87 fields (885 ha) straddling the Niedersachsen / Sachsen-Anhalt border.
- **The 43 western fields (`state = 'NI'`)** have state soil data from LBEG (NIBIS): Bodenzahl and soil class.
- **The 44 eastern fields (`ST`)** only have global data, so the LBEG layers there are `unavailable` with a reason. That's a feature, not a bug: the API must always say *why* a layer is missing.
- **7 sliver fields** (`use_for_stats = 0`) have no usable NDVI history. Their yield potential comes from the soil/terrain model alone: a near-flat map with `low` confidence.

## Parameters and sources

| parameter | soilgrids | lbeg_bk50 | lbeg_bodenschaetzung | derived | best |
|---|---|---|---|---|---|
| `texture` | clay % (stats add sand, silt, USDA class) | – | Bodenart class (categorical: S, lS, …) | – | – |
| `ph` | ✓ | – | – | – | – |
| `soc` | ✓ | – | – | – | – |
| `nfk` | ✓ (mm, 0–100 cm) | always `unavailable` (not in downloaded data / outside NI) | – | ✓ (mm, nFKWe from BÜK200 + KA5) | ✓ derived > soilgrids |
| `bodenzahl` | – | – | ✓ (west only) | ✓ (model trained on the west, whole farm) | ✓ lbeg_bodenschaetzung > derived |
| `yield_potential` | – | – | – | ✓ index, 100 = field mean (model `yield_v1`, normal-spring scenario) | – |

"–" means `not_applicable`. The table `source_parameters` holds exactly the ✓ cells and the `lbeg_bk50` row; any other pair is `not_applicable`.

**`best` is the reconciled layer:** for each pixel it takes the first source in the ranking that has a value, together with that source's interval and confidence. Its GeoTIFF has a **5th band `source_code`**; the codes are in the file's `source_codes` tag and in the response. For `best` layers the response carries an extra block. Pass it through as-is:

```jsonc
"source_mask": {
  "png_url": "/static/runs/.../bodenzahl__best__source.png",   // same bounds as the layer PNG
  "raster_url": "/static/runs/.../bodenzahl__best.tif#band=5",
  "colormap": {"type": "categorical", "classes": [{"value": 1, "code": "lbeg_bodenschaetzung", "color": "#1b7837"}, ...]}
}
```

`stats.source_shares` gives the share of the stats zone that each source supplied, e.g. `{"lbeg_bodenschaetzung": 0.55, "derived": 0.45}`. Read it from `field_layers.source_png_path` and `provenance_json.source_colormap` (see `assemble_response()`).

## DB: what to query

```sql
-- the run to serve
SELECT run_id, data_as_of_json FROM runs WHERE is_current = 1;

-- match a feature by plotId (or by geometry hash, see matching rules)
SELECT plot_id, field_name, bounds_json, geom_geojson FROM fields WHERE plot_id = ?;
SELECT plot_id FROM fields WHERE geom_hash = ?;

-- every precomputed layer of a field
SELECT * FROM field_layers WHERE run_id = ? AND plot_id = ?;

-- which (source, parameter) pairs exist at all → otherwise not_applicable
SELECT source, parameter FROM source_parameters;

-- colour scales (returned verbatim as "colormap")
SELECT colormap_id, json FROM colormaps;

-- optional, e.g. for an "about the data" page: validation metrics of the derived layers (see poc/VALIDATION.md)
SELECT metric, scope, value, n FROM validation WHERE run_id = ?;

-- the area you can answer for (polygons outside → outside_coverage_area)
SELECT geom_geojson FROM coverage_areas WHERE name = 'farm_raster_extent';
```

`field_layers` columns you map into the response:
- `status`, `reason`, `coverage`, `unit`
- `stats_json` and `confidence_json`: parse and return them as objects.
- `colormap_id`: look up in `colormaps`.
- `geotiff_path`, `png_path`, `conf_png_path`: relative to `poc/store/`. Serve them as `/static/<path>`.
- `provenance_json`

Geometries are GeoJSON text in EPSG:4326, so no SpatiaLite is needed. Use shapely for the geometry work.

## Endpoint contract

### `POST /soil/layers`

**Request.** This is the spec request: a FeatureCollection plus `parameters` and `sources`. See `samples/request.json`.
- If `parameters` or `sources` is missing, return all of them.
- Unknown values → 422.
- More than 200 features → 413.

**Response.** See `samples/response.json`. It has this shape:

```jsonc
{
  "run_id": "poc-2026-10-03",
  "data_as_of": {"sentinel2": "2026-10-03", "weather": "2026-09-27", ...},
  "fields": [{
    "id": "f1",                          // echo of feature.id
    "matched_plot_id": "MoYIfvnid4wXBDha0wJ3",
    "match": "plot_id",                  // plot_id | geometry | clipped | outside_coverage_area
    "field_name": "Heuweg",
    "bounds": [[S, W], [N, E]],          // lat/lon, for Leaflet imageOverlay
    "layers": [                          // one entry per requested parameter × source, always
      {
        "parameter": "ph", "source": "soilgrids",
        "status": "ok", "reason": null, "coverage": 1.0, "unit": "pH",
        "png_url": "/static/runs/.../ph__soilgrids.png",
        "geotiff_url": "/static/runs/.../ph__soilgrids.tif",
        "stats": {"mean": 6.23, "std": .., "min": .., "p10": .., "p50": .., "p90": .., "max": .., "n_px": .., "zone": "inner_20m"},
        "colormap": {"type": "continuous", "unit": "pH", "stops": [[4.5, "#a50026"], ...]},
        "confidence": {
          "level": "low", "interval_90": [4.56, 7.87],
          "drivers": ["single_coarse_source", "range_crosses_threshold:liming_ph_5.5"],
          "pixel_shares": {"low": 1.0, "medium": 0.0, "high": 0.0},
          "raster_url": "/static/runs/.../ph__soilgrids.tif#band=4",
          "png_url": "/static/runs/.../ph__soilgrids__conf.png"
        },
        "provenance": {"native_resolution_m": 250, "grid": "EPSG:32632 10 m"}
      },
      {"parameter": "bodenzahl", "source": "lbeg_bodenschaetzung", "status": "unavailable",
       "reason": "outside_source_region:niedersachsen", "coverage": 0.0, "unit": "points"}
    ]
  }]
}
```

**How this differs from the original spec, and why:**
- `layers` is a **list**, not a dict keyed by parameter. Every requested pair gets an entry, including unavailable and not-applicable ones, each with a reason.
- There are additional fields: `status`, `reason`, `coverage`, `confidence`, `provenance`, `match`, plus `run_id` / `data_as_of` at the top.
- Everything in the spec is still there: `bounds`, `png_url`, `geotiff_url`, `stats`, `unit`, `colormap`.

### Statuses and reasons (closed lists)

| status | when | reasons you'll see |
|---|---|---|
| `ok` | source covers ≥ 95 % of the field | – |
| `partial` | covers some of it | `only_parcels_at_sample_point_downloaded`, `partial_source_coverage` |
| `unavailable` | source should provide it but doesn't here | `outside_source_region:niedersachsen`, `attribute_not_in_downloaded_data`, `no_parcel_downloaded_for_field`, `outside_coverage_area`, `no_data_in_source` |
| `not_applicable` | the source never has this parameter | `source_does_not_provide_parameter` (not stored in the DB; you generate it) |

Only `ok` and `partial` layers have files, stats, colormap and confidence.

### Confidence block

`level` (low/medium/high), `interval_90`, `drivers` and `pixel_shares` come straight from `confidence_json`. You only add the two URLs.
- `interval_90` is `null` for categorical layers.
- The per-pixel confidence is band 4 of the GeoTIFF: 1 low, 2 medium, 3 high.
- `__conf.png` hatches only the low pixels and can be drawn on top of the layer PNG with the same `bounds`.

Driver codes:
- `single_coarse_source`
- `pixel_larger_than_field`
- `range_crosses_threshold:liming_ph_5.5`
- `range_crosses_threshold:nfk_90_140_mm`
- `range_wider_than_texture_class`
- `range_wider_than_half_value`
- `official_survey_1to5000`
- `interval_assumed_not_calibrated`
- `partial_coverage`
- `no_inner_zone_edge_pixels_only`
- `ndvi_proxy_not_yield`
- `no_harvest_data_for_validation`
- `edge_strip_soil_model_weighted`
- `soil_model_only`
- `error_calibrated_west`
- `buek200_1to200000_nearest_point`
- `reconciled_best_source_per_pixel`
- `mixed_sources_in_field`
- `no_official_survey_model_only`
- `lookup_table_approximate`
- `model_trained_on_38_parcels`
- `extrapolated_across_state_border`
- `range_crosses_threshold:bodenzahl_30_50`
- `no_ndvi_history`
- `few_ndvi_seasons`
- `unstable_or_edge_pixels`

The method behind them is in `UNCERTAINTY.md`. Expect SoilGrids layers to be mostly `low`: its 90 % ranges are very wide on this farm. That's real and is part of the demo story.

### Static files

Mount `poc/store/` at `/static/`. Paths contain the run id and never change, so send `Cache-Control: public, max-age=31536000, immutable`.
- **PNG overlays** are RGBA in EPSG:3857 and are transparent outside the field. Put them on a Leaflet map with `L.imageOverlay(png_url, bounds)`, where `bounds` is the field's `bounds`.
- **GeoTIFFs** are 4-band COGs in EPSG:32632 (UTM 32N, 10 m): value, lo90, hi90, confidence. Nodata is NaN.

### Other endpoints

- `GET /soil/fields`: known fields as a GeoJSON FeatureCollection (plotId, name, area, state, use_for_stats).
- `GET /soil/runs/current`: `run_id`, `data_as_of`.
- `GET /health`

## Field matching

Apply these rules in order, per feature:

1. `properties.plotId` is in `fields` → `match: "plot_id"`. If the posted geometry is very different from the stored one (IoU < 0.95), still serve it but use `match: "plot_id_geometry_differs"`.
2. No plotId, but the geometry matches a known field: either the same `geom_hash` (see `geom_hash()` in `build_store.py`: coordinates rounded to 6 decimals, sha1, 16 hex chars), or IoU ≥ 0.95 → `match: "geometry"`.
3. Not a known field, but inside `farm_raster_extent` → `match: "clipped"`. This is **phase B** (below). Until then, return every layer as `unavailable`, reason `not_precomputed_for_this_polygon`.
4. Otherwise → `match: "outside_coverage_area"`. Every applicable layer is `unavailable` with reason `outside_coverage_area`, and `bounds` is `null`.

## Work plan

**Phase A: known fields (start here)**
1. FastAPI + pydantic v2 models for the request and response. Open the DB read-only (`file:...?mode=ro`).
2. `POST /soil/layers` with matching rules 1, 2 and 4. Build the layers list from `source_parameters` × the request, then fill each entry from `field_layers`.
3. Static serving of `poc/store/` under `/static/`.
4. Contract test: posting `samples/request.json` must return `samples/response.json`. Compare as JSON, ignoring key order and float noise.
5. A single HTML page with Leaflet:
   - fields from `GET /soil/fields`;
   - click a field → call `/soil/layers` → show the layer PNG with a toggle for the confidence hatch;
   - a legend from `colormap`;
   - a status badge and `drivers` for each layer.

**Phase B: new polygons inside the farm**

Clip `regional_rasters` with rasterio. The same 4 bands, same grid and same colormaps apply. Then:
- compute stats on the polygon shrunk by 20 m (10 m for yield). If that leaves nothing, use the whole polygon and set `stats_zone = full_field_fallback`.
- Yield potential: divide the regional value by the zone mean and multiply by 100.
- Render the PNG in EPSG:3857.
- Cache the results under `geom_hash`.

`publish`/`build_field` in `build_store.py` does exactly this for the known fields; reuse it.

**Phase C: nice to have**
- `run_id` in the request to pin a run.
- An OpenAPI example taken from `samples/`.
- A Dockerfile.

## Acceptance checks

- `samples/request.json` → `samples/response.json`.
- An east field never shows LBEG data, but does show `derived` nFK and Bodenzahl. A west field shows Bodenzahl from both `lbeg_bodenschaetzung` (`ok` or `partial`) and `derived`.
- `best` Bodenzahl on a partly surveyed west field (e.g. `Bocksenden`) has a `source_mask` and `stats.source_shares` with both sources; on an east field only `derived`.
- The sliver `Sandberg - 2` returns `yield_potential` as `ok` with `low` confidence and drivers `soil_model_only`, `no_ndvi_history`. Its stats use `full_field_fallback`.
- The Hildesheim polygon returns 200 with every layer `unavailable` / `outside_coverage_area`. It must not return 404 or 500.
- PNG overlays line up with the field outlines in Leaflet.
- No outbound network calls during a request. You can check this by running with the network disabled.

## Not your problem (data side)

How values are computed, confidence rules, yield model improvements, the 14-day refresh. If you need a new column or file, ask; don't derive it in the API.
