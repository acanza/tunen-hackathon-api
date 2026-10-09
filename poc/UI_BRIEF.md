# UI brief: Seggerde soil app (POC)

For the people building the app that consumes our API. The API contract (endpoints, JSON, statuses, files)
is in [`API_BRIEF.md`](API_BRIEF.md); this document is about **what to show, how, and what the data can and
can't support today**. Numbers below come from the current store (run `poc-2026-10-03`, 87 fields, 885 ha).

Each feature below is marked:
- ✅ **Available**: everything is in the API today.
- 🟡 **Partly available**: buildable now, with a gap noted.
- 🔴 **Needs data work**: the data side still has to produce it. A proposed JSON shape is given so you can
  build against a mock now; the field names are a proposal to agree on with the API developer.

## The farm, in four facts that shape the UI

1. **It straddles a state border.** 43 western fields (Niedersachsen) have the official soil survey
   (Bodenschätzung); 44 eastern fields (Sachsen-Anhalt) don't. Everywhere, the UI must say *why* a layer is
   missing (`status` + `reason`), never just leave a gap.
2. **The soils are poor and sandy** (Bodenzahl 17–49) and **water is the limiting factor**.
3. **Most soil values are uncertain.** With the confidence rules in [`../UNCERTAINTY.md`](../UNCERTAINTY.md),
   pH, SOC, nFK and SoilGrids texture are `low` confidence on **every** field: their 90 % range crosses the
   decision threshold (liming pH 5.5, nFK 90/140 mm). This is correct, not a bug, and it is the story of
   features 1–3: *"we can't tell from public data whether this field needs lime → sample here"*.
4. **There is no harvest data.** Yield potential is a *relative* index from 8 years of satellite NDVI
   (100 = the field's own average), not tonnes per hectare.

## Concepts the UI must handle everywhere

| Concept | Where it comes from | UI rule |
|---|---|---|
| `status` | each layer: `ok`, `partial`, `unavailable`, `not_applicable` | `unavailable` → show the reason in plain language (table at the end). `not_applicable` → hide the layer for that source. `partial` → show it, with a "covers N % of the field" badge (`coverage`). |
| `confidence.level` | `high`, `medium`, `low` per field; per pixel in GeoTIFF band 4 | Badge colour + the masking rule below. Never colour alone: always the word too. |
| `confidence.interval_90` | field-level 90 % range | Show as "likely 5.4–6.2". |
| `confidence.drivers` | machine codes | Translate with the driver table at the end (farmer text / audit text). |
| `source` | `soilgrids`, `lbeg_bk50`, `lbeg_bodenschaetzung`, `derived`, `best` | Default to `best` where it exists, otherwise the most detailed available source. |
| `bounds` | `[[S,W],[N,E]]` per field | `L.imageOverlay(png_url, bounds)`; all PNGs of a field share it. |
| `stats.zone` | `inner_20m`, `inner_10m`, `full_field_fallback` | Small print: "statistics exclude the 20 m field edge". |

### The masking rule (required): uncertain zones are grey-hatched, never shown as values

| Pixel confidence | Render |
|---|---|
| high | Layer colour |
| medium | Layer colour + light hatch |
| low | **Grey + hatch. No layer colour.** On hover: the range and the reason, never a single value |
| no data | Transparent, with the `reason` in the legend/tooltip |

What exists today: the layer PNG (`png_url`, coloured everywhere) and `confidence.png_url` (dark hatch on low
pixels only). Drawing the hatch over the coloured PNG still shows colour under the hatch, so **it does not
meet the rule yet**. Two ways to meet it:
- **Proposed (data side, small):** a third PNG per layer, `masked_png_url`: colour where high/medium, opaque
  grey + hatch where low. The UI just draws it. This is the recommended route.
- **UI-only fallback:** read band 4 of `geotiff_url` with `georaster` + `georaster-layer-for-leaflet` and paint
  low pixels grey yourself.

Expect pH, SOC, nFK and SoilGrids texture maps to be **entirely grey** under this rule. Design the empty state for
it: "Public data can't settle this here. See the sampling plan (feature 3)."

---

## What you can build today

These screens run on today's API, files and `samples/response.json`. They need no new data work. Build them now; the
data-side additions listed at the end slot into these screens without changing their layout.

| Screen | Feature | Reads | Limitation today |
|---|---|---|---|
| **1. Farm overview map** | – | `GET /soil/fields`; per field `POST /soil/layers` | – |
| **2. Field view: property maps** | 1 | `png_url` + `bounds`, `confidence.png_url`, `colormap`, `stats`, `confidence`, `status`/`reason`/`coverage` | Strict grey masking only via band 4 of the GeoTIFF client-side, until `masked_png_url` exists |
| **3. Yield view** | 0 | `yield_potential` / `derived` layer, `validation` table | Within-field only; no comparison between fields |
| **4. Before/After demo** | 2 | the same parameter from each source, then `best` + `source_mask` + `stats.source_shares` | Side-by-side comparison only; no conflict heatmap yet |
| **5. Parcel spec sheet** | 5 | all layers of a field, `sources`, `source_parameters`, `validation`, `data_as_of` | Farmer sentences are templated in the UI |
| **6. About the data** | 5 | `sources`, `validation`, `runs` | LBEG/BGR licences show "not verified" |

### 1. Farm overview map
- All 87 fields, coloured by state (`fields.state`: NI = official survey available, ST = not) or by any field statistic.
- Click a field → `POST /soil/layers` for that field → field view.
- Summary line: 885 ha, 43 fields with the official survey, 44 without.

### 2. Field view: property maps
- **Layer switcher:** texture, pH, SOC, nFK, Bodenzahl, yield potential. **Source switcher:** `soilgrids`,
  `lbeg_bodenschaetzung`, `derived`, `best`. Default to `best` where it exists.
- Map: `L.imageOverlay(png_url, bounds)`, with the low-confidence hatch (`confidence.png_url`) as a toggle on top.
- Legend from `colormap` (continuous or categorical).
- Side panel per layer:
  - value (`stats.mean`, p10–p90) and "likely X–Y" (`interval_90`);
  - confidence badge with its word;
  - drivers in plain language (driver table at the end);
  - coverage badge for `partial`.
- Unavailable layers are greyed out in the switcher, with the reason in words.
- **Masking rule today:** read band 4 of `geotiff_url` with `georaster-layer-for-leaflet` and paint low pixels grey.
  Once `masked_png_url` arrives, swap the overlay for it.

### 3. Yield view
- Relative yield map, diverging around 100, with the confidence hatch.
- **"Your usual yield" input** (e.g. 7.5 t/ha) → expected t/ha per zone (TIF band 1 × input / 100) and for the field.
  This is pure client-side maths.
- Text from the stats: "10 % of the field is at least 3 % below its average" (p10/p90).
- A "how we know" box from the `validation` table: tested on held-out seasons, 70 % of pixels on the correct side of the field average.

### 4. Before/After demo
- **Before:** one western field, the same parameter from each source side by side, e.g. Bodenzahl
  `lbeg_bodenschaetzung` (covers part of the field) | `derived`, and nFK `soilgrids` (~190 mm everywhere) vs
  `derived` (83–174 mm).
- **After:** the `best` layer with the `source_mask` overlay (green = official survey, purple = model),
  `stats.source_shares` ("55 % official survey, 45 % model") and the confidence badge.
- Demo fields: `Bocksenden`, `Altenaer Weg`, `Cawi-Wiese`.

### 5. Parcel spec sheet
- **Audit view (complete):** every layer with value, `interval_90`, confidence, drivers (audit text), source
  with scale, licence and pull date (`sources`), method (`source_parameters.method`), `data_as_of`, and
  validation metrics (`validation`).
- **Farmer view (templated in the UI for now):** sentences assembled from the layers and the driver table, e.g.
  "Soil quality: Bodenzahl about 31 (official survey)." or "Water: the soil holds about 110 mm, which is low,
  so dry springs matter." Give each sentence a marker linking to its audit row.
- Print/PDF of both views.

### 6. About the data
- Source table with licences, validation numbers and the run date, straight from the DB.

### Not buildable today
- Sampling plan (3), management signals (4) and crop suitability (6).
- Conflict heatmap (2), field-to-field yield comparison (0), and data-side farmer sentences (5).

Build against the proposed shapes below with mock data if you want to start on these screens early.

---

## 0. Expected yield by field 🟡

**What exists:** `yield_potential` / `derived`, a 10 m map per field, **100 = the field's average**. Above 100 means
a consistently stronger part of the field, below 100 a weaker one. Validated by predicting a held-out season:
70 % of pixels land on the correct side of the field average ([`VALIDATION.md`](VALIDATION.md)).
Confidence: 76 fields `medium`, 2 `high`, 9 `low` (the 7 sliver fields have no satellite history).

**What it is not:** tonnes per hectare, and not a comparison *between* fields.

**Recommended UI:**
- A map with a diverging colour scale around 100 (the `colormap` is provided), labelled "relative to this field's average".
- **"Enter your usual yield" input** (e.g. 7.5 t/ha winter wheat). The UI then shows *expected yield per zone* =
  the farmer's average × index / 100, and the field total. This is honest: the farmer supplies the level, we supply the
  pattern. Do this client-side; no API change is needed.
- Zone shares from `stats` (p10/p90) as "10 % of the field is at or below 97".

**Gap (🔴, proposed):** a between-field productivity rank (each field's average rank of peak NDVI among the farm's
fields over 8 seasons). The data is on disk. Proposed field-level addition:
```jsonc
"field_summary": {"productivity_rank_pct": 72, "seasons": 8, "note": "crop mix not known; weak signal"}
```

## 1. Property maps with confidence (0–30 cm) 🟡

| Parameter | Best source to show | Depth | Today |
|---|---|---|---|
| Texture | `lbeg_bodenschaetzung` class (west, partial) → else `soilgrids` clay % | survey class / 0–30 cm | ✅ |
| pH | `soilgrids` | 0–30 cm | ✅ (low everywhere) |
| Organic C | `soilgrids` (`soc`, g/kg) | 0–30 cm | ✅ (low everywhere) |
| nFK | `best` (derived > soilgrids) | **effective rooting depth (~60–110 cm), not 0–30 cm** | ✅ (low everywhere) |
| Bodenzahl | `best` (official > derived) | not depth-based (whole profile) | ✅ (8 high, 15 medium, 64 low) |

- **Per pixel:** value = band 1, range = bands 2–3, confidence = band 4 of `geotiff_url`. **Per field:** `stats`
  + `confidence.interval_90` + `confidence.level`.
- Label nFK and Bodenzahl with their real depth meaning: nFK is plant-available water in the root zone, the
  standard agronomic definition.
- Texture has two encodings: the official class (categorical: S, Sl, lS…) and SoilGrids clay %. Show the class
  where `coverage > 0` and fall back to clay %. The legend comes from `colormap` (categorical or continuous).
- Masking rule as above.

## 2. Source discrepancy map: key demo visual 🟡

**Before/After narrative, buildable today:**
- **"Siloed sources (Before)":** three small maps of the same field side by side, e.g. Bodenzahl `lbeg_bodenschaetzung`
  (covers only part of the field) | `derived` | nFK `soilgrids`. Each source tells a different or incomplete story;
  SoilGrids nFK is ~190 mm everywhere, while our derived nFK ranges from 83 mm on dry sand to 174 mm on peaty soil.
- **"Confidence fusion (After)":** the `best` layer with its `source_mask` overlay (green = official survey,
  purple = model) and the confidence hatch. Good demo fields: `Bocksenden`, `Altenaer Weg`, `Cawi-Wiese` (west, mixed sources).

**Gap (🔴, proposed):** a true discrepancy layer, where sources disagree by more than their combined uncertainty
(z = |a − b| / √(σa² + σb²)). The pairs available on this farm:
- nFK: `derived` vs `soilgrids`, which disagree strongly almost everywhere;
- Bodenzahl: `lbeg_bodenschaetzung` vs `derived`, which agree closely in the west;
- texture: SoilGrids clay vs the survey class, which disagree (SoilGrids can't tell S from lS, see VALIDATION §5).

Proposed as an extra parameter-level source:
```jsonc
{"parameter": "nfk", "source": "discrepancy", "status": "ok",
 "png_url": "...nfk__discrepancy.png",            // 0 = agree … 3+ = strong conflict (σ units)
 "stats": {"share_conflict": 0.92, "pairs": ["derived", "soilgrids"]},
 "explanation": "SoilGrids water-holding is nearly constant on this sandy farm; the soil-profile estimate varies 83–174 mm"}
```

## 3. Optimised sampling plan 🔴

**Rule:** sample where the uncertainty could change a decision, not where variance is highest. For pH that means
the probability that the true pH is on the other side of the liming threshold:
`p = Φ((threshold − value) / σ)`, `decision_uncertainty = 1 − |2p − 1|` (1 = coin flip, 0 = settled).

**Proposed data-side output** (per field, precomputed; endpoint `GET /soil/fields/{plotId}/sampling-plan`, or a
block in the field response):
```jsonc
"sampling_plan": {
  "points": [
    {"rank": 1, "lat": 52.3512, "lon": 11.0931, "decision": "liming", "parameter": "ph",
     "decision_uncertainty": 0.94, "current_estimate": 5.6, "interval_90": [4.9, 6.4],
     "why": "pH estimate is right at the liming threshold (5.5); one sample settles it for ~6 ha"}
  ],
  "rules": {"min_spacing_m": 50, "edge_buffer_m": 20, "max_points": 5},
  "covers_ha": 31.2
}
```
**UI:** numbered markers, a list with the "why", and **export as GPX/CSV** for the phone or GPS.

**Feedback loop (Level B):** a later `POST /soil/samples` with lab results (point, depth, pH, SOC, texture) lets the
data side recalibrate SoilGrids locally on the next run. For the POC, show it as a disabled "Upload lab results" button
with a tooltip; don't build the endpoint yet.

## 4. Management signals 🔴

Five signals per field, each with one keyword only: `Probable`, `Possible`, `Unlikely`, `No`, `Unknown`.
**No doses, no rates, no product names.**

| Signal | Based on (all in the store today) | Expected on this farm |
|---|---|---|
| Liming | pH vs threshold for the texture (sand 5.3–5.5) | mostly `Possible` / `Unknown` (SoilGrids too uncertain) |
| Drought risk | nFK `best` + dry-spring water balance + yield sensitivity | `Probable` on the dry sand fields (nFK ~83 mm) |
| Erosion | slope (terrain) + texture; on this flat sandy farm wind matters more than water | water `Unlikely`; wind `Possible` on sand |
| Compaction | texture + wetness index (no traffic or bulk-density data) | mostly `Unknown` / `Possible` on wet gley fields |
| Nitrate leaching | sandy texture + low nFK + winter rain surplus | `Probable` on sand |

**Proposed shape** (per field):
```jsonc
"signals": [
  {"signal": "drought_risk", "keyword": "Probable", "probability": 0.8,
   "because": ["nfk_best_below_90_mm", "dry_spring_in_3_of_8_seasons"],
   "farmer_text": "Dry spells are likely to limit this field: it holds little plant-available water.",
   "audit": {"inputs": {"nfk_best_mm": 83, "cwb_apr_jun_dry_mm": -185}, "rule": "nFK < 90 mm and dry-spring frequency ≥ 30 %"}}
]
```
Keyword mapping (proposed): probability ≥ 0.7 `Probable`, 0.4–0.7 `Possible`, 0.15–0.4 `Unlikely`, < 0.15 `No`;
`Unknown` when the inputs are `unavailable` or the deciding input is `low` confidence *and* its range spans the
whole scale. **UI:** icon + keyword + one sentence; never colour alone.

## 5. Parcel spec sheet (dual view) 🟡

One page per field, two tabs. Everything for the audit view is in the API today; the farmer sentences need the driver
table below (and later the signals/suitability blocks).

| | Farmer view | Audit view |
|---|---|---|
| Content | 4–6 plain sentences: soil quality, water, pH/lime, yield pattern, what to sample | Every layer: value, `interval_90`, confidence, drivers (audit text), source |
| Example | "This field has poor, sandy soil (Bodenzahl about 31). It holds little water, so dry springs hit it hard. We can't tell from public data whether it needs lime: one soil sample at point 1 would settle it." | `ph / soilgrids: 6.2 (likely 4.6–7.9), low: single coarse source, 250 m pixel larger than field, range crosses liming threshold 5.5` |
| Sources | "Based on the state soil survey and satellite images 2019–2026" | Source table with scale, licence and pull date (`sources` table: SoilGrids CC BY 4.0, Copernicus open data, LBEG/BGR licence *not verified*), method per layer (`source_parameters.method`), validation metrics (`validation` table, `VALIDATION.md`) |
| Data date | "Data as of 3 Oct 2026" (`data_as_of`) | `run_id`, `data_as_of` per source |

- **Print/PDF** of the sheet: both views, with the map snapshot.
- **The licence gap is real:** LBEG and BGR terms were not verified. Show "licence not verified" in the audit view rather than hiding it.
- The "15 % auditability requirement" is met by the audit view, provided every number on the farmer view can be traced
  to a row in the audit view. Keep that 1:1 link (e.g. a footnote marker per sentence).

## 6. Crop suitability 🔴

Crops: wheat, barley, rye, rapeseed, maize (corn), sugar beet, potato, grassland. Rating: `Well adapted` |
`With limitations` | `Poorly adapted`, **always with the limiting factor** when not well adapted.

**Proposed data-side rules** (to be implemented on the store; thresholds are agronomic rules of thumb and will be listed
in the audit view):

| Factor (from the store) | Used for |
|---|---|
| nFK `best` (mm) | water demand: sugar beet, maize, wheat, rapeseed need more; rye and potato tolerate low |
| Bodenzahl `best` | general fertility: wheat and sugar beet want good soils; rye fits poor sand |
| pH (SoilGrids, uncertain) | barley and sugar beet sensitive to low pH; potato tolerant (scab risk at high pH) |
| Texture class | heavy vs light soil; potato and rye like light sand |
| Wetness (TWI, gley soil units) | grassland fine on wet gley; arable crops limited by waterlogging |
| Dry-spring water balance | drought exposure for spring-sown crops |

**Proposed shape** (per field):
```jsonc
"crop_suitability": [
  {"crop": "sugar_beet", "rating": "Poorly adapted", "limiting_factors": ["low_available_water"],
   "text": "Sugar beet: Poorly adapted. Limiting factor: low available water capacity (≈ 83 mm).",
   "confidence": "medium", "inputs": {"nfk_best_mm": 83, "bodenzahl_best": 24}},
  {"crop": "rye", "rating": "Well adapted", "limiting_factors": [], "text": "Rye: Well adapted.", "confidence": "medium"}
]
```
**UI:** an 8-row table with a rating chip and the limiting factor in words. If the deciding input is `low` confidence,
add "(uncertain: based on coarse data)".

---

## What's left for the data side, in suggested order

| # | Item | Unblocks |
|---|---|---|
| 1 | `masked_png_url` (grey-hatched low pixels) | feature 1 masking rule |
| 2 | Management signals block | features 4, 5 |
| 3 | Sampling plan | feature 3 |
| 4 | Discrepancy layers | feature 2 (true conflict map) |
| 5 | Crop suitability block | feature 6 |
| 6 | Between-field productivity rank | feature 0 |

Until then, build against the proposed shapes with mock data; everything else above works with today's API.

## Suggested demo script (5 minutes)

1. **The farm:** map of 87 fields, coloured by state. "Half the farm has no state soil survey."
2. **Before:** one western field, three source maps side by side. They disagree, and one covers only part of the field.
3. **After:** the `best` map with the source mask and confidence. "One map, and it tells you where it's sure."
4. **Honesty:** the pH map is grey-hatched. "Public data can't decide liming here", which leads to the sampling plan
   with 5 GPS points.
5. **Yield pattern:** the relative yield map. Enter "7.5 t/ha" and see the expected yield per zone.
6. **Spec sheet:** the farmer view, then flip to the audit view: every number traced to a source and a licence.

## Driver codes: farmer and audit text

| Code | Farmer text | Audit text |
|---|---|---|
| `single_coarse_source` | Based on a coarse global map only. | Single source, SoilGrids 250 m. |
| `pixel_larger_than_field` | The map is coarser than this field. | Field smaller than one 250 m SoilGrids cell (6.25 ha). |
| `range_crosses_threshold:liming_ph_5.5` | Can't tell whether liming is needed. | 90 % range crosses pH 5.5. |
| `range_crosses_threshold:nfk_90_140_mm` | Can't tell how much water the soil holds. | 90 % range crosses 90 or 140 mm. |
| `range_crosses_threshold:bodenzahl_30_50` | Soil quality class uncertain. | 90 % range crosses Bodenzahl 30 or 50. |
| `range_wider_than_texture_class` | Soil type uncertain. | 90 % range wider than one texture class. |
| `range_wider_than_half_value` | Organic matter estimate rough. | 90 % range wider than half the value. |
| `error_calibrated_west` | Checked against the state survey nearby. | Interval from RMSE vs Bodenschätzung, 37 parcels (VALIDATION §5). |
| `official_survey_1to5000` | From the official soil survey. | Bodenschätzung, LBEG, 1:5 000. |
| `interval_assumed_not_calibrated` | | Interval ±5 points assumed. |
| `partial_coverage` | Only part of the field is covered. | Source covers < 95 % of the field. |
| `no_inner_zone_edge_pixels_only` | Field too narrow for reliable values. | No pixels ≥ 20 m from the edge; full field used. |
| `buek200_1to200000_nearest_point` | From the federal soil overview map. | BÜK200 1:200 000 unit at the nearest sample point. |
| `lookup_table_approximate` | Estimated from soil-profile tables. | KA5 lookup values approximate (±30 mm at 90 %). |
| `model_trained_on_38_parcels` | Estimated by our model. | Trained on 38 Bodenschätzung parcels; CV RMSE 6.9 points. |
| `extrapolated_across_state_border` | Estimated from neighbouring Lower Saxony. | Model applied outside its training region (Sachsen-Anhalt). |
| `reconciled_best_source_per_pixel` | Best available source used for each spot. | Per-pixel ranking; see `source_mask`. |
| `mixed_sources_in_field` | Parts of the field come from different sources. | > 1 source in the stats zone; see `stats.source_shares`. |
| `no_official_survey_model_only` | No official survey here: estimated by our model. | Bodenzahl from the model only. |
| `ndvi_proxy_not_yield` | Based on crop growth seen from satellites. | Relative peak NDVI (Sentinel-2), not yield. |
| `no_harvest_data_for_validation` | Not checked against harvests. | No yield-monitor or harvest data. |
| `edge_strip_soil_model_weighted` | The field edge is less certain. | Outer 10 m from the soil/terrain prior. |
| `soil_model_only` / `no_ndvi_history` | No satellite history for this field: pattern unknown. | No usable NDVI; soil/terrain prior only (R² ≈ 0). |
| `few_ndvi_seasons` | Few years of satellite data. | Median < 6 usable seasons. |
| `unstable_or_edge_pixels` | The pattern changes between years in parts of the field. | > 25 % of pixels low (unstable zone or edge). |

## Reasons for missing layers (`status: unavailable`)

| Reason | Farmer text |
|---|---|
| `outside_source_region:niedersachsen` | The state soil survey only covers Lower Saxony; this field is in Saxony-Anhalt. |
| `attribute_not_in_downloaded_data` | This value exists in the state map but isn't in our data yet. |
| `no_parcel_downloaded_for_field` | The survey covers this field, but we haven't loaded it yet. |
| `outside_coverage_area` | Outside the area we have data for. |
| `no_data_in_source` | The source has no value here. |
