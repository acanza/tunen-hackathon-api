# Sentinel-2 NDVI layer for LuF Seggerde (2019 – 2026-10-03)

This layer measures variation *within* each field. The soil maps are too coarse to show it: 44 of 87 fields are smaller than one SoilGrids pixel. The source is Sentinel-2 L2A at 10 m, from Element84 Earth Search. It needs no account and reads COGs from the public AWS bucket with HTTP range requests only.
Pulled 2026-10-03. Every season from 2019 to 2026 was fetched, so nothing was skipped.

## Files

| File | What it is |
|---|---|
| `fetch_s2.py` | Search, windowed reads, SCL masking, NDVI, per-season stacks and peak composites. Uses only the farm bbox, not the field polygons. `uv run fetch_s2.py [--years 2026]` |
| `field_stats.py` | Per-field statistics, relative productivity, zones, summary and PNGs. `uv run field_stats.py` |
| `scene_catalogue.csv` | **One row per observation** (date × platform): item ids, MGRS tile(s), processing baseline, `boa_offset_applied`, offset implied by metadata vs offset actually subtracted, eo:cloud_cover, footprint coverage of the window, SCL class shares, `valid_frac` over the window, used yes/no + reason, median red/NIR DN over vegetation, seconds |
| `ndvi_stack_<year>.tif` | Every used scene of the season. int16 NDVI×10000, nodata −32768, band description = `obs_id`. About 21–46 MB per season |
| `ndvi_peak_<year>.tif` | Peak-season composite over **May–Jul**: band 1 = p90 of clear observations, band 2 = max, band 3 = number of clear observations (float32) |
| `field_ndvi_timeseries.csv` | Long format: `plotId, fieldName, date, obs_id, ndvi_mean, ndvi_p10, ndvi_p50, ndvi_p90, valid_fraction, valid_obs, stat_zone, use_for_stats`. Area-weighted with exactextract on the 20 m inner buffer |
| `field_season_peaks.csv` | Per field × season: mean, SD and CV of peak NDVI (p90) over the 10 m inner zone, plus the status used for normalisation |
| `relative_productivity.tif` | Band 1 = mean over seasons of (pixel peak NDVI / field mean). Band 2 = SD of that ratio across seasons. Band 3 = mean within-field z-score. Band 4 = SD of the z-score across seasons (stability). Band 5 = number of seasons |
| `yield_potential_zones.tif` | uint8 with a colour table: 1 stable-high, 2 stable-low, 3 unstable, 0 none |
| `field_summary.csv` | **One row per field**: clear observations per season, max May–Jul NDVI per season, peak p90 and within-field CV per season, mean CV, zone shares, p10/p90 of relative productivity, mean SD of z |
| `quicklook_timeseries.png`, `quicklook_relative_productivity.png`, `quicklook_zones.png` | Quicklooks |
| `grid_and_params.json`, `field_stats_meta.json`, `fetch_log.txt` | Grid definition, thresholds, which field file was used, run log |
| `raw/items/*.json` | All 1005 STAC items returned by the searches (the items used are listed in the catalogue) |
| `raw/boa_offset_check*.json` | Evidence for the BOA-offset handling (see below) |

Disk use is about 325 MB. The per-season stacks account for 274 MB of that and can be deleted if only the composites are needed.

## Grid

**EPSG:32632, 10 m, 728 × 894 px**, bounds `(637580, 5797800, 644860, 5806740)`. That is the farm bbox (lon 11.025–11.122, lat 52.315–52.390) plus 200 m of padding.
The grid is snapped to 20 m multiples, so it lines up exactly with the S2 10 m grid and with the 20 m SCL grid (every SCL pixel covers exactly 2×2 NDVI pixels).
Every item over the farm reports `proj:epsg = 32632`, and the script asserts this on every read.

## Recipe

1. **Search.** `sentinel-2-l2a`, bbox = farm, 1 Mar–31 Oct of each year (2026 up to today), `eo:cloud_cover < 60`. This returned 1005 items. `eo:cloud_cover` is for the whole 110 km tile, so it is only a coarse pre-filter.
2. **Deduplicate into observations.** An observation is one acquisition date and one platform. Two kinds of duplicates exist:
   - **MGRS tiles 32UPD and 32UPC overlap.** 32UPD covers 100 % of the farm window; 32UPC covers only about 22 %, the southern strip. Tiles are ranked by how much of the window their footprint covers. The best tile is read first, and the next one only fills its nodata pixels. In practice, 298 used observations came from 32UPD alone, 3 from 32UPC alone (32UPD was over 60 % cloud that day), and 1 was a mosaic of both.
   - **Earth Search keeps `_0` and `_1` items for the same tile and date.** The `_1` items are the ESA Collection-1 reprocessing (baseline 05.00). The script keeps the highest baseline and then the highest sequence. As a result, 253 of 302 used scenes are baseline 05.xx, 40 are 04.00 and 9 are 02.xx/03.xx.
3. **Windowed reads.** SCL (20 m) is read first. If the scene is already below the valid threshold, red and NIR are never read. This happened for 145 observations, at about 0.8 s each. Otherwise B04 and B08 are read at 10 m, which takes about 3.7 s per observation (median) for the three reads. The script used 6 threads. A full 2019–2026 run takes about 11 minutes, and a single season 30–60 s. The search itself takes 5–11 s per season. Bytes transferred were not measured.
4. **Cloud mask.** Keep SCL 4 (vegetation), 5 (not vegetated / bare soil) and 6 (water). Drop 0 nodata, 1 saturated/defective, 2 dark area, 3 cloud shadow, 7 unclassified, 8/9 cloud medium/high, 10 thin cirrus and 11 snow. Classes 3, 8, 9 and 10 are also dilated by 40 m (2 SCL pixels).
5. **Scene filter.** A scene is kept when `valid_frac ≥ 0.20` over the whole window. One more scene was dropped as a snow/haze suspect (see the gotchas). Per field, a time-series row counts as a clear observation (`valid_obs`) when at least 50 % of the field's stats zone is clear. Partly cloudy scenes are kept per pixel.
6. **NDVI.** `(B08 − B04) / (B08 + B04)` on DN, after the offset check below.
7. **Peak composite.** For each pixel and season, the p90 of clear May–Jul observations, plus the max and the observation count.
8. **Field statistics** (`field_stats.py`). exactextract computes coverage-weighted mean, p10, p50, p90 and count on the 20 m inner buffer. When that buffer is empty, the full field is used and `stat_zone = full_field_fallback`. `valid_fraction` = clear pixel area / zone area.

### Scenes per season

| Season | STAC items | Observations | Used | Used May–Jul | Median clear obs per field |
|---|---|---|---|---|---|
| 2019 | 150 | 47 | 31 | 12 | 25 |
| 2020 | 193 | 58 | 46 | 12 | 33 |
| 2021 | 161 | 52 | 26 | 10 | 18 |
| 2022 | 107 | 61 | 42 | 18 | 31 |
| 2023 | 71 | 42 | 30 | 15 | 23 |
| 2024 | 85 | 49 | 35 | 13 | 26 |
| 2025 | 127 | 77 | 47 | 13 | 41 |
| 2026 (to 3 Oct) | 111 | 62 | 45 | 19 | 39 |

2025 and 2026 have more scenes because Sentinel-2C is in orbit. Some 2026 scenes from early October may still be missing from the catalogue.

## Gotchas found

### BOA offset (processing baseline ≥ 04.00, from 2022-01-25)
- **Earth Search COG pixels are already harmonised: the −1000 DN offset is already removed.** Do not subtract it again.
- **Proof** (`raw/boa_offset_check.json`). The same scene (2021-06-18, 32UPD) exists as `_0` (baseline 03.00, `boa_offset_applied: false`, `raster:bands offset: 0`) and as `_1` (baseline 05.00, `boa_offset_applied: true`, `raster:bands offset: −0.1`). Over the 8456 pixels that are vegetation in both, the median DN differs by **+5 (red) and 0 (NIR)**. NDVI is 0.735 vs 0.732. Applying the advertised −1000 DN to the 05.00 item would push NDVI to 0.999.
- **The STAC metadata is inconsistent.**
  - `raster:bands.offset = −0.1` appears on **every** baseline ≥ 04.00 asset, even where the pixels are already harmonised. Generic readers that apply scale/offset automatically (stackstac, odc-stac, `rioxarray mask_and_scale`) would double-correct these items.
  - Some items (2022 baseline 04.00 and 05.10, 2025-03 baseline 05.11; 11 items, 7 of them used) say `earthsearch:boa_offset_applied: false`. Yet their raw red DN reach 84–139 and the 0.5th percentile is 150–240 (`raw/boa_offset_check_flagged.json`), which is impossible if +1000 were still in the pixels. A first run trusted that flag. It produced veg red DN of 64–88 in March and NDVI shifted upward, so it was fixed.
- **Rule in `fetch_s2.py`.** Subtract 1000 only if the metadata says the offset is present *and* the pixels agree (0.5th percentile of raw red DN in the window ≥ 1000). In this run, no item met both conditions, so **no offset was subtracted anywhere**. The catalogue keeps `dn_offset_by_metadata` next to `dn_offset_subtracted` so disagreements stay visible.
- **Consistency check.** Median red DN over SCL vegetation in used scenes is 243–920 (median 490) and stable across 2019–2026, with no jump at 2022.

### Other gotchas
- **A bright DN floor flags snow or frost.** On 2024-03-04, SCL called 99.6 % of the window clear (bare soil), but red DN p0.5 was 3420 and NDVI about 0.04. This is snow or frost misclassified by SCL. Such scenes are now dropped (`reason = bright_dn_floor_suspect_snow_or_haze`).
- **`eo:cloud_cover` is tile-wide.** Scenes with 55–60 % tile cloud were sometimes 99 % clear over the farm, and scenes with 0 % tile cloud were sometimes useless. SCL over the window is what decides.
- **Undetected haze remains.** Some scenes have farm-median NDVI clearly below their neighbours (e.g. 2023-07-15), probably thin haze that SCL missed. The p90 composite is robust to this. Single dates in the time series are not.
- **Two tiles and two sequences** are both described in Recipe step 2.
- **The SCL 2 (dark area) and 7 (unclassified) classes are dropped.** This is conservative: some wet or dark soil is lost.

## Field statistics

- **Fields file:** `../clean/fields_clean.geojson` (87 fields, 80 with `use_for_stats = true`), recorded in `field_stats_meta.json`. The script falls back to `../fields_active.geojson` when the clean file is missing.
- The time series covers **all 87 fields** and carries `use_for_stats`. Seven fields have no 20 m inner area (Eichenkoppel, Lange Wiese Schonfläche, Lehmkuhle, Nachthude 1, Papenberg Brache, Parkwiese, Sandberg - 2), so they use the full field and are flagged `full_field_fallback`. They are all `use_for_stats = false`.
- Relative productivity, zones and the summary metrics cover only the **80 `use_for_stats` fields**.

### Relative productivity and zones (yield potential)

1. **Normalise each season.** Take the pixel's peak NDVI (p90 May–Jul, needing at least 2 clear observations). Compare it with the field's mean over its **10 m inner zone**: the pixels whose centre lies at least 10 m inside the field. This drops mixed edge pixels. Two outputs are computed: the ratio `rel = NDVI / field_mean` and the z-score `z = (NDVI − field_mean) / max(field_sd, 0.02)`. The 0.02 floor keeps near-uniform, saturated seasons from turning noise into large z values. A field-season is skipped if the field mean is below 0.40 or fewer than 50 % of its zone pixels are clear. Neither rule triggered: all 80 fields × 8 seasons were used.
2. **Combine across seasons** (at least 3 required): mean and SD of `rel` and of `z`.
3. **Zones**, after Blackmore's classic spatial × temporal scheme:
   - **unstable**: SD(z) > 1.0
   - **stable-high**: otherwise, and mean z > 0
   - **stable-low**: otherwise, and mean z ≤ 0

Fields with fewer than 20 zone pixels (0.2 ha) get no zones. None of the 80 hit this limit.

**Using this as the yield-potential layer.** `relative_productivity.tif` band 1 is the continuous index: 1.0 is the field mean, and 0.9 means 10 % below the field's typical peak NDVI. `yield_potential_zones.tif` is the classified version. A sensible next step is to smooth band 1 (e.g. a 3×3 median) and cut 2–3 classes per field, then join it with the DEM (wetness index) and the BÜK200 units to *explain* the zones. Stable-low patches on the Gley or Anmoor units would be wet spots, and on BBn units drought-prone sand.

### Per-field highlights (`field_summary.csv`)

**Overall**
- Farm-wide, the median field has 55 % stable-high, 34 % stable-low and 8 % unstable area.
- The high/low split is uneven because low patches are fewer but deeper: the field mean is pulled down by a low tail.

**Strongest within-field variation** (mean CV of peak NDVI across seasons)

| Field | Area | Mean CV | Notes |
|---|---|---|---|
| Specksbreite Brache | 10.5 ha | 13.5 % | rel p10–p90 = 0.87–1.15. A fallow strip, so heterogeneous cover is expected |
| Kotenphöre | 3.7 ha | 10.3 % | |
| Specksbreite Groß | 8.2 ha | 9.2 % | |
| Silbersee | 13.7 ha | 8.4 % | 71 % stable-high with a compact stable-low patch |
| Ribbensdorf Grünland | 2.4 ha | 8.4 % | |
| Saalsdorfer Breite | 7.5 ha | 8.1 % | |
| Wolfskuhle | 24.3 ha | 8.1 % | 19 % unstable |
| Kantorplan | 13.8 ha | 7.9 % | |

**Most unstable**
- Berg (16.9 ha, 21 %), Plantage, Wolfskuhle, Springphör and Röken: each about 18–21 % unstable area.
- On the zone map, unstable pixels cluster along headlands and field borders and in a few interior patches.

**Most uniform**
- Small fields: Ackern Viehtrift (ÖVF), Porzelle, Am Wehr and Kaserne, with CV 0.7–1.5 %.
- Their zone split is mostly noise, so the zones should not be used for management there.

**Visual check**
- The relative productivity map shows clear, persistent within-field patterns in the large fields south of the village (See, Masch, Langes Feld, Mittelbreite, Klinzerbreite). That is where zoning pays off.
- It also shows faint diagonal striping, a known S2 detector/along-track artefact. Smoothing removes it.

## Crop-rotation caveat

- **Peak NDVI differs by crop and by year.** Per field and season, the date of maximum NDVI falls in May for 251 field-seasons, July for 190, June for 74 and August–October for 129. This mix reflects winter cereals and rapeseed peaking in May/June, maize and beet in Jul–Sep, grassland cut several times, and catch crops in autumn. That is why absolute peak NDVI is never compared across fields or years. Each season is normalised within the field first (`rel`/`z`), and only then are seasons averaged.
- **May–Jul still misses some crops.** Maize sown in May only reaches its peak in late July or August, so the p90 composite under-represents it. Pixels that emerged late in that season can look low. This is one source of instability. **Crop-aware windows** (a peak window per crop and year from the farm's rotation records, or the date of each field's NDVI maximum) would be the next improvement.
- **Grassland** (Wiese, Koppel, Grünland) is cut or grazed several times. Its peak reflects the cutting schedule more than yield potential.
- **NDVI saturates above about 0.85** in dense canopies, which compresses the differences between good and very good areas. Within-field CVs of 2–5 % are therefore meaningful. A red-edge index (NDRE from B05/B8A at 20 m) would separate dense canopies better. The script reads only B04, B08 and SCL; adding B05 is one extra read per scene.

## 14-day automatic refresh

1. Run `uv run fetch_s2.py --years <current year>`. It re-searches the current season and rebuilds that season's stack and peak composite in about 1 minute. Previous seasons are left untouched, and their catalogue rows are kept.
2. Run `uv run field_stats.py`, which recomputes the time series, relative productivity, zones, summary and PNGs (about 20 s).

To make it incremental, store the last item `updated` timestamp and query STAC with `datetime=<last_run>/..`. Earth Search sometimes adds `_1` reprocessed items or updates items weeks later, so re-searching the whole current season is safer and still cheap. From November to February the job only needs to run if winter scenes are wanted. The season window is Mar–Oct; a crop-aware version would extend it.

## Limitations

- SCL misses some haze and thin cloud and sometimes mislabels snow. Single-date values carry this noise; composites are more robust.
- **NDVI is a proxy for vigour, not yield.** The zones are relative within each field and have not been checked against yield-monitor data. Absolute values from different fields or crops are not comparable.
- **10 m pixels, 10 m inner zone.** Fields under about 1 ha have few pixels, and their zones are weak.
- **Overlapping fields.** When rasterising, smaller fields are drawn last, so they win where fields overlap.
- **Bytes transferred were not recorded.** The run made one SCL window read per tile per observation and red + NIR reads for the 302 used observations. Read times are in `scene_catalogue.csv` (`seconds`).
- **2026 has no autumn yet.** Its stability numbers include a season that ended on 3 Oct.
