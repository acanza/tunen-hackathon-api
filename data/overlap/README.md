# Repeated data across sources (Seggerde farm)

This report covers two kinds of repetition: the same quantity coming from more than one source, and the same values stored more than once in our own files. For each overlap it checks whether the copies agree, and says which one to keep.
It covers the 87 active fields of LuF Seggerde and was built from the files already in `data/` on 2026-10-03, with no new downloads.

| File | Content |
|---|---|
| `overlap.py` | Builds everything below. `uv run overlap.py` (offline) |
| `texture_by_field.csv` | Per field: SoilGrids 0–30 cm (clay, sand, silt, SOC, bulk density, field capacity, wilting point) next to the BÜK200 topsoil class, GÜK200 geology and NIBIS, with `*_agrees` flags |
| `elevation_by_field.csv` | Copernicus DEM field mean vs the elevation Open-Meteo reports for the field's point |
| `moisture_by_cell.csv` | ERA5 soil moisture per ERA5 cell vs SoilGrids field capacity and wilting point of the fields in that cell |
| `file_duplicates.csv` | Files or columns that hold the same values twice |
| `summary.json` | Every number quoted here |

SoilGrids values are the median (`Q0.5`) averaged over 0–30 cm, weighted by depth. They use the 20 m inner zone where it exists and the full field otherwise. BÜK200 values come from the topsoil horizon of the **dominant reference profile** of the field's dominant unit.

## Summary

| Quantity | Sources holding it | Agree? | Keep |
|---|---|---|---|
| Clay / texture | SoilGrids (%), BÜK200 (KA5 class), NIBIS Bodenschätzung (class, 4 fields) | **No.** Agrees on 20 of 87 fields | BÜK200 for the soil pattern, SoilGrids for a number with uncertainty |
| Organic carbon / humus | SoilGrids SOC, BÜK200 humus class | **No.** Agrees on 12 of 87 fields | BÜK200 for wet/organic soils |
| Bulk density | SoilGrids `bdod`, BÜK200 packing class Ld | Yes, 87 / 87 (but the check is coarse) | SoilGrids |
| Soil type / wetness | BÜK200, NIBIS BK50 (4 fields) | Mostly, 3 of 4 | BÜK200 (BK50 only covers part of the farm) |
| Parent material | BÜK200 substrate, GÜK200 geology | Yes, ~80 % of the area | Either. GÜK200 has real polygons |
| Elevation | Copernicus DEM 30 m, Open-Meteo `elevation` | Yes, median gap 0.65 m | DEM. Open-Meteo's value is the same kind of data, coarser |
| Soil water | SoilGrids field capacity / wilting point, ERA5 soil moisture | Not comparable as absolute values | ERA5 for timing, SoilGrids for capacity |
| Soil moisture over time | ERA5 archive, ICON forecast | **No overlap**: different days and depth bands | Both, kept separate |
| SoilGrids tiles | 2 downloads (`raw/soilgrids`, `soilgrids/raw`) + a fixed copy | Same source, different resampling | One pull (see below) |
| Field geometry | 3 field layers | 7 fields differ | `clean/fields_clean.geojson` |

## A. The same quantity from several sources

### Texture: SoilGrids vs BÜK200 vs Bodenschätzung

SoilGrids sees almost no difference between soil units that BÜK200 maps as very different. Clay ranges only 4.8–14.1 % across all 87 fields:

| BÜK200 unit | Fields | ha | BÜK200 topsoil | BÜK200 clay % | SoilGrids clay % (min / median / max) | Fields where they agree |
|---|---|---|---|---|---|---|
| 392606 Pseudogley-Braunerde on till | 15 | 345 | Sl2 | 5–8 | 5.6 / 9.7 / 14.1 | 20 % |
| 392611 Braunerde on outwash sand | 26 | 204 | Su2 | 0–5 | 4.8 / 6.8 / 10.1 | 19 % |
| 392630 Gley / Anmoorgley | 12 | 154 | Sl3 | 8–12 | 5.8 / 9.0 / 9.6 | 92 % |
| 392603 Gley-Tschernitza on floodplain loam | 22 | 130 | **Ls3** | **17–25** | 4.8 / 9.3 / 13.8 | **0 %** |
| 392621 Gley to Moorgley | 7 | 34 | Uls | 8–17 | 4.8 / 5.7 / 6.8 | 0 % |
| 392604, 392636, 392637 | 5 | 17 | Ls3 / Sl3 / Sl4 | 8–25 | 6.7–13.5 | 1 of 5 |

- The biggest miss is the floodplain loam (392603). BÜK200 says loam with 17–25 % clay, and SoilGrids says sandy loam with about 9 %.
- On the sand unit 392611 (BÜK200: 0–5 % clay), SoilGrids gives up to 10 %.
- The **Bodenschätzung** (NIBIS layer L849) returned data for 4 of the 13 fields queried. All 4 classes are sands:
  - `S5D` (Bodenzahl 17) and `Sl3D` (37) on the BÜK200 sand unit, which agrees with BÜK200.
  - `lS4Al` (42 and 48) on two floodplain fields. That is lighter than BÜK200's `Ls3` loam and closer to SoilGrids.

  Its classes measure "abschlämmbare Teile" (particles < 0.01 mm), not clay, so they can't be compared exactly with either source.
- KA5 class → % clay uses the standard KA5 table, which the services don't deliver. Agreement means the SoilGrids median falls inside the class range.

### Organic carbon: SoilGrids SOC vs BÜK200 humus class

SoilGrids SOC is 13–21 g/kg on every field. BÜK200 humus classes convert to anything from 5.8 g/kg to 87 g/kg (SOC = humus / 1.72):

| BÜK200 unit | BÜK200 humus | → SOC g/kg | SoilGrids SOC median |
|---|---|---|---|
| 392630 wet Gley / Anmoorgley | **h5** | 46–87 | 14.8 |
| 392603 floodplain | h4 | 23–47 | 15.5 |
| 392606, 392611 (till / sand) | h2 | 6–12 | 15 |
| others | h3 | 12–23 | 14–18 (agrees) |

SoilGrids underestimates carbon in the wet organic soils and overestimates it in the sandy ones. This is the same peat blind spot the EDA sites showed at Teufelsmoor (see `../README.md`).

### Bulk density: SoilGrids vs BÜK200 packing class

All 87 fields agree. SoilGrids gives 1.42–1.45 kg/dm³, and every dominant BÜK200 topsoil is Ld2 (1.4–1.6). The check is weak, though: both sources are close to constant over the farm, and Ld is effective packing density, not dry bulk density.

### Soil type and parent material: BÜK200 vs NIBIS BK50 vs GÜK200

- **BK50** (NIBIS L816) returned a soil type for 4 of the 13 fields queried; the other 9 came back empty. BK50 and BÜK200 agree on 3 of the 4:
  - `Nachthude 2` and `Umfeldwiese`: BK50 "Tiefer Gley" matches BÜK200's Gley soils on floodplain loam.
  - `Kurze Enden vor Biogas`: BK50 "Podsol-Braunerde" matches BÜK200's Braunerde on sand.
  - `Altenaer Weg` is the exception: BK50 says "Tiefer Podsol-Gley" (groundwater at 5–11 dm), while BÜK200 says dry Braunerde on sand.
  - The farm's README says NIBIS was "not queried". In fact `raw/nibis/` holds these 26 responses, so that note is out of date.
- **GÜK200 vs BÜK200** agree on about 80 % of the area. That figure counts each field's area under its dominant unit in each map. Till (`D,,Lg`) matches the units on till, meltwater sand (`D,,gf`) matches the outwash sand unit, and fluvial deposits (`,,f`, `w,,f`) match the floodplain and Gley units. The largest mismatch is 26 ha of Triassic bedrock (`su`) under the till unit 392606.
  - GÜK200 returns real polygons, while BÜK200 withholds geometry, so GÜK200 is the better source for boundaries.
  - The two maps are separate products, so their agreement is a real cross-check.

### Elevation: Copernicus DEM vs Open-Meteo

Open-Meteo returns an `elevation` value with every response, taken from a 90 m DEM. Across the 87 field points it differs from our 30 m DEM field mean by:
- median 0.65 m
- 90th percentile 1.8 m
- maximum 8.2 m

On 84 of 87 fields (97 %) it falls inside the field's elevation range. At the EDA sites the gap is −4 to +7 m.

This is repeated data, not new information. Use the DEM and ignore Open-Meteo's value, except as the height ERA5 was corrected to.

### Soil water: SoilGrids vs ERA5

The two sources describe the same soil water, but not in the same units of meaning:
- SoilGrids gives capacity: field capacity 31–34 %, wilting point 8–14 % (vol, 0–30 cm). Both barely change across the farm.
- ERA5 gives state over time. Over 2026-09-03 → 2026-10-02 it ranged 19–34 % at 0–7 cm and 19–24 % at 7–28 cm.

ERA5 never reached SoilGrids field capacity and never dropped below its wilting point in any of the 4 cells. At the EDA sites over 2025, ERA5 often sat *above* field capacity. ERA5 has its own soil texture map, so its absolute values can't be read against SoilGrids. Use ERA5 for relative wetness and timing only.

### Soil moisture over time: ERA5 archive vs ICON forecast

There is no overlap. The archive ends 2026-10-02 23:00 and the forecast starts 2026-10-03 00:00. The depth bands also differ: ERA5 uses 0–7 / 7–28 / 28–100 / 100–255 cm, ICON uses 0–1 / 9–27 cm. They can't be spliced into one series without a depth mapping.

Copernicus SWI (`../swi_eda/`) would be a third source of the same quantity, but it hasn't been pulled yet: only the STAC catalogue is saved.

### Repetition inside one source

Several tables repeat a single value across many fields because the source grid is coarser than the fields:
- **Open-Meteo:** 87 rows of `openmeteo_fields.csv` hold only **4** distinct soil-moisture means and **2** distinct 30-day rain totals. Weather and moisture are farm-level.
- **SoilGrids:** **44** fields are smaller than one 250 m pixel, so they repeat their neighbours' values.

## B. The same values stored twice in our files

| What | Copies | Same values? | Action |
|---|---|---|---|
| SoilGrids tiles: `seggerde/raw/soilgrids/` (fetch.py, 268 tiles) and `seggerde/soilgrids/raw/` (soilgrids_rasters.py, 395 tiles incl. `uncertainty`) | 2 | Same source, but WCS resampled each pull onto its own grid (pixel 250.88 m vs 250.78 m, 42×39 vs 43×38). At matching pixels about 50 % of values are identical; the rest are off by about one neighbouring pixel (e.g. clay mean |Δ| 0.7 % points) | Keep one pull. The raster pull is the superset; rebuild `soilgrids_fields.csv` from it |
| `seggerde/raw/soilgrids/` vs `seggerde/raw/soilgrids_fixed/` | 2 | Identical (only CRS added and 0 → NaN) | Keep only `soilgrids_fixed/` |
| `LuF-Seggerde-Dev-fields.geojson` archived vs active features | 2 | 86 of 87 archived features are exact copies | Already handled by `clean/` |
| `seggerde/fields_active.geojson` vs `seggerde/clean/fields_clean.geojson` | 2 | 80 of 87 identical. 7 differ by 1.89 ha in total (the overlap cuts) | SoilGrids, BÜK200, DEM and Open-Meteo statistics use `fields_active`, Sentinel-2 uses `fields_clean`. Re-run those stages on `fields_clean` |
| `field_coverage.csv` | copies columns of `soilgrids_fields`, `buek200_fields`, `dem_fields`, `openmeteo_fields` | Yes (elevation checked: 87 / 87) | Fine as a summary, but regenerate it whenever a source changes |
| `guek200_eda/guek200_dominant.csv` ⊂ `guek200_fields.csv` | 2 | Yes, 87 / 87 | It is farm data in an EDA folder; move it to `seggerde/` |
| `sentinel2/field_summary.csv` `cv_<year>` vs `field_season_peaks.csv` `peak_cv` | 2 | Yes, 640 / 640 | Wide copy of the long table; fine |
| `openmeteo_eda/compare_soilgrids_fc_wp.csv` | copies SoilGrids `wv0033` / `wv1500` for the EDA sites | n/a | Fine; it is a comparison table |

## What this means

1. **For soil texture and carbon, the two soil sources contradict each other on most fields.** They are not interchangeable copies.
   - BÜK200 shows the farm's real pattern: sand vs till vs floodplain loam vs wet organic soils.
   - SoilGrids flattens that pattern into one sandy-loam value.
   - Don't average the two. Use the BÜK200 unit as the soil class, and SoilGrids only as a number with its uncertainty band.
2. **Elevation, field geometry and the SoilGrids tiles are true duplicates.** Pick one copy of each:
   - elevation: DEM
   - field geometry: `fields_clean.geojson`
   - SoilGrids tiles: one pull

   Then rebuild the per-field tables so that every source uses the same field layer.
3. **Weather and soil moisture are one value per ~9 km cell.** Repeating them per field adds rows, not information.
