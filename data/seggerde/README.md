# LuF Seggerde farm: data coverage per field

What each EDA source returns for the fields in `../../LuF-Seggerde-Dev-fields.geojson`, and where values are missing.
Pulled 2026-10-03.

## Files

| File | What it is |
|---|---|
| `fetch.py` | Pulls all sources for the farm. `uv run fetch.py [stage ...] [--force]`; stages: `soilgrids nibis buek200 dem openmeteo`. Raw responses are cached in `raw/`. |
| `coverage.py` | Joins the per-source outputs into `field_coverage.csv`. `uv run coverage.py` |
| `field_coverage.csv` | **One row per active field**: area checks, SoilGrids pixels and missing share, BÜK200 units, DEM pixels and slope, ERA5 cell, NIBIS status |
| `fields_active.geojson` | The 87 active fields, geometry repaired, plus computed area, inner area (20 m buffer) and a representative point |
| `soilgrids_fields.csv` | Per field × property × depth × statistic: area-weighted mean/min/max, full field and 20 m inner zone |
| `buek200_points.csv` / `buek200_fields.csv` | Soil unit at each sample point / unit area share per field |
| `dem_fields.csv` | Elevation and slope statistics per field, full and inner zone |
| `openmeteo_fields.csv` | ERA5 / ICON grid cell per field, null shares, 30-day rain and ET₀ |
| `raw/` | Untouched responses: SoilGrids GeoTIFFs (`soilgrids/`) and repaired copies with CRS + nodata (`soilgrids_fixed/`), BÜK200 JSON + profile HTML, DEM window + slope raster, Open-Meteo JSON |

Statistics use [exactextract](https://github.com/isciences/exactextract), which weights each pixel by the share of it inside the field.

## The field file

| Check | Result |
|---|---|
| Features | 174 = **87 active + 87 archived** |
| Archived features | 86 are exact copies of an active field (name usually prefixed with a number, e.g. `37 Mittelbreite`); only `Hof` (3.09 ha) has no active counterpart. See `clean/fields_audit.csv`. (An earlier version of this README said 84; that matching method paired small sub-fields with the larger field around them.) |
| Active area | 876.9 ha by the `area` column, 885.4 ha computed from the geometry |
| `area` vs `subsidyArea` | Identical on every field |
| Field size | 0.001 ha to 54.4 ha, median 6.2 ha |
| Invalid geometry | 1 (`Wolfskuhle (ÖVF)`), repaired with `make_valid` |
| Extent | lon 11.025–11.122, lat 52.315–52.390 (Sachsen-Anhalt, near the Niedersachsen border) |

**`area` doesn't always match the polygon.** 6 fields are larger than their stated area, by up to 4.4 ha (`Wolfskuhle`: 20.4 ha stated, 24.8 ha drawn). The stated area is probably the net or subsidy area, but we didn't verify that.

**Some active fields overlap:**
- `Lange Wiese` × `Lange Wiese Schonfläche`: 1.41 ha
- `Wolfskuhle` × `Wolfskuhle (ÖVF)`: 0.45 ha
- 4 more pairs at ≤ 0.02 ha each

Overlapping fields count the same ground twice in any farm total.

**Tiny fields:** `Sandberg - 2` (0.001 ha) and `Parkwiese` (0.019 ha) are slivers, too small to hold a single DEM pixel. 7 fields disappear entirely when shrunk by 20 m.

## Coverage by source

| Source | Fields with data | Missing | Notes |
|---|---|---|---|
| SoilGrids (WCS, 250 m) | 87 / 87 | 1 field partly (`Abraham`: 5.8 % of its area has no prediction) | **44 fields are smaller than one pixel**, so their values come from pixels mostly covering neighbouring land |
| BÜK200 (1:200k) | 87 / 87 | none | 8 soil units on the farm; 20 fields contain 2–3 units |
| Copernicus DEM (30 m) | 87 / 87 | none | 2 fields cover less than 1 pixel |
| Open-Meteo ERA5 (~9 km) | 87 / 87 | **last ~5 days null** (archive lag, last value 2026-09-27 23:00 UTC) | All 87 fields fall in **4 cells**; ICON forecast: 16 cells, no nulls |
| NIBIS BK50 + Bodenschätzung | **unknown** | not queried | See below |

### SoilGrids
- Fetched with the **WCS raster service**, not the REST API: 268 rasters (11 properties × 6 depths × 4 statistics + `ocs`) in about 1.5 minutes, instead of 30–45 s per point.
- Request in the native Homolosine grid (`SUBSET=X(...)&SUBSET=Y(...)` in metres); a lat/lon subset comes back resampled (~155 × 265 m).
- **The GeoTIFFs carry no CRS and no nodata value.** `0` means "no prediction". `fetch.py` assigns `+proj=igh` and turns `0` into NaN.
- Topsoil 0–5 cm, median per field across the farm:

| Property | Min | Median | Max |
|---|---|---|---|
| clay % | 4.2 | 6.8 | 14.3 |
| sand % | 53.9 | 62.9 | 70.7 |
| pH | 4.6 | 6.1 | 6.9 |
| SOC g/kg | 19.6 | 26.5 | 39.3 |
| wv0033 (field capacity) vol % | 36.2 | 38.0 | 38.8 |
| wv1500 (wilting point) vol % | 8.1 | 11.4 | 14.4 |

- Uncertainty is large. Median over fields of the 5–95 % range: clay 0.6–65 %, SOC 7–288 g/kg, pH 4.1–7.7.
- Medians of clay, sand and silt don't add to 100 % (only means do, by construction).
- Field capacity is nearly constant (36–39 %) across sandy and loamy fields, which suggests SoilGrids can't separate water holding here.

### BÜK200
- **The service withholds polygon geometry** (`geometry: null` in JSON and GeoJSON), so it can't be intersected with the fields. Unit shares were estimated from 591 point queries on a 125 m grid inside the fields; small fields get only 1–2 points.
- The farm sits on one map sheet: CC3926 Braunschweig (layer 18).

| Unit | Short legend | Farm share | Meaning |
|---|---|---|---|
| 392606 | SS-BB, SS-BB-LF | 38 % | Pseudogley-Braunerden on till cover sand over till loam (stagnant water) |
| 392611 | BBn | 22 % | Braunerden on cover sand over outwash sand (dry, sandy) |
| 392630 | GNn, GGn, GMn | 17 % | Wet Gleye and Anmoorgleye (high groundwater) |
| 392603 | GG-AT | 15 % | Gley-Tschernitzen on floodplain loam/silt |
| 392621 | GGn, GGhh, HN-GH | 5 % | Gleye to Moorgleye, partly peat |
| 392636, 392604, 392637 | | 2 % | Braunerden/Ranker on rhyolite, Vegen, Braunerden on sandy loess |

SoilGrids' fairly uniform sandy-loam picture hides this mix of dry sand, stagnant water, wet groundwater soils and some peat.

### DEM
- One tile (`N52 E011`), 308 × 257 pixel window, pixel 28.3 × 30.7 m.
- Elevation 69–110 m, mostly flat: field mean slope median 1.1°.
- **Field edges inflate slope.** The 90th-percentile slope drops by more than 1° on 21 fields after removing a 20 m edge strip (median 2.0° → 1.6°). Hedges and tree lines at the edges are in the surface model.

### Open-Meteo
- One request for all 87 points each for archive (last 30 days) and forecast (7 days).
- All fields share 4 ERA5 cells (34 / 27 / 25 / 1 fields), so weather and soil moisture are **farm-level, not field-level**.
- Last 30 days: 23–32 mm rain vs ~60 mm ET₀.
- The last 6 days of the archive window are null.

### NIBIS (BK50 + Bodenschätzung): unresolved
- The farm is outside Niedersachsen, so we expected empty results. A direct test at `11.07, 52.35` did return an empty `FeatureCollection` within 0.4 s.
- But the point inside `Nachthude 2` (`11.0669, 52.3587`) **returned a BK50 polygon after 22 s**. So NIBIS has *some* data over at least part of the farm, maybe a polygon that crosses the state border.
- Further requests timed out (8 s, then 80 s) or were refused. The server probably throttled us after the retries. Nothing was saved, and `field_coverage.csv` marks NIBIS as not queried.
- To do: retry later, sequentially, with a 60 s timeout and pauses. Check the `BL_NAME` (federal state) attribute of what comes back.

## Missing values: summary

| What | Fields affected |
|---|---|
| SoilGrids no prediction | 1 field, 5.8 % of its area |
| SoilGrids pixel larger than field | 44 fields (values reflect neighbouring land) |
| No inner zone after 20 m edge buffer | 7 fields (statistics only for the full field) |
| DEM < 1 pixel | 2 fields (`Sandberg - 2`, `Parkwiese`) |
| BÜK200 unit share from 1–2 points only | about 30 fields (small fields) |
| Open-Meteo archive | last ~5 days null for every field |
| NIBIS BK50 / Bodenschätzung | all 87 unknown |
| Sachsen-Anhalt state soil data (LAGB) | not explored |
| Satellite data | not explored |

## What this means for the challenge

- **This farm is SoilGrids + BÜK200 territory** unless NIBIS turns out to cover it. The equivalent detailed state source would be Sachsen-Anhalt's (LAGB), which we haven't looked at.
- **Field geometry is a data-quality problem in itself:** archived duplicates, overlaps, slivers, stated areas that don't match the polygons. Clean it before computing any statistic, and use only active fields.
- **Soil maps can't resolve differences inside a field here.** Half the fields are smaller than one SoilGrids pixel, and BÜK200 is 1:200k. Within-field variation has to come from satellite history and the DEM.
- **Use the 20 m inner buffer for statistics**, and fall back to the full field only when the buffer leaves nothing.
