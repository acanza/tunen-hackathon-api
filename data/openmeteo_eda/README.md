# Open-Meteo EDA: ERA5-Land archive + DWD ICON forecast (soil moisture & soil temperature)

Our role for this source: **the time dimension of the soil profile**, meaning how wet and how warm the soil is
at a point, hour by hour, in the past (reanalysis) and the next 7 days (forecast). SoilGrids/BÜK give
static properties; Open-Meteo gives the dynamic state.

Fetched 2026-10-03 (UTC). REST, JSON, no API key.

## Files

| File | What |
|---|---|
| `fetch.py` | Reproducible fetch (`uv run fetch.py`, add `--force` to re-download). Skips files that already exist. |
| `analyze.py` | Flattens raw JSON to CSV, computes the summaries, compares with SoilGrids, draws plots (`uv run analyze.py`). |
| `raw/*.json` | Untouched API responses. `raw/_requests_log.json` has the exact URL, latency and size of each request. |
| `era5land_2025_hourly_wide.csv` | 8 sites × 8760 h, 8 columns (SM + ST at 4 ERA5-Land depth bands). Time is UTC. |
| `era5land_2025_hourly_long.csv.gz` | Same data in long format: `site,time,quantity,depth_band,value,unit` (gzipped, about 43 MB uncompressed). |
| `era5_2025_daily.csv` | Daily `precipitation_sum`, `et0_fao_evapotranspiration` (from `era5_seamless`) plus daily means of SM/ST (UTC days). |
| `forecast_icon_seamless_hourly.csv` / `_daily.csv` | ICON seamless, 7 past days + 7 forecast days, ICON depth bands. |
| `forecast_icon_models_hourly.csv` | icon_d2 / icon_eu / icon_global side by side (column suffix = model). |
| `forecast_ecmwf_ifs025_hourly.csv` | ECMWF IFS 0.25° forecast with **ERA5-style** depth names. |
| `grid_cells.csv` | Requested coordinates compared with the returned grid cell per model, distance, and elevation. |
| `summary_soil_moisture_by_site_depth.csv` | Min/p05/median/p95/max/range, wettest/driest month, soil temperature stats. |
| `compare_soilgrids_fc_wp.csv` | ERA5-Land SM per band compared with SoilGrids wv0033 (FC) / wv1500 (WP), Q0.5. |
| `plot_soil_moisture_2025.png`, `plot_soil_temperature_2025.png` | Small multiples (one panel per site, one line per depth band). |

## Endpoints and working requests

Multi-location works: comma-separated `latitude=` / `longitude=` lists return a **JSON array** (one object per
location, in request order). All 8 sites × 1 year × 8 hourly variables came back in **one request** (4.4 MB, about 10 s).

**(1) Archive, ERA5-Land, hourly soil** (`https://archive-api.open-meteo.com/v1/archive`)
```
https://archive-api.open-meteo.com/v1/archive?latitude=52.22,53.05,52.75,53.35,53.25,51.75,52.37,53.55
 &longitude=9.95,10.05,7.35,8.4,8.9,9.55,9.73,9.95&start_date=2025-01-01&end_date=2025-12-31
 &hourly=soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_moisture_28_to_100cm,soil_moisture_100_to_255cm,
         soil_temperature_0_to_7cm,soil_temperature_7_to_28cm,soil_temperature_28_to_100cm,soil_temperature_100_to_255cm
 &models=era5_land&timezone=UTC
```
**(1b) Archive, daily water balance.** Use `models=era5_seamless`, not `era5_land` (see the gotchas below).
```
https://archive-api.open-meteo.com/v1/archive?latitude=...&longitude=...&start_date=2025-01-01&end_date=2025-12-31
 &daily=precipitation_sum,et0_fao_evapotranspiration&models=era5_seamless&timezone=UTC
```
`era5_seamless` returns soil values identical to `era5_land` (checked) and also fills precipitation/ET₀ from ERA5,
so a production call can use **one request with `models=era5_seamless`** for everything.

**(2) Forecast, DWD ICON** (`https://api.open-meteo.com/v1/forecast`)
```
https://api.open-meteo.com/v1/forecast?latitude=...&longitude=...
 &hourly=soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,soil_moisture_3_to_9cm,soil_moisture_9_to_27cm,soil_moisture_27_to_81cm,
         soil_temperature_0cm,soil_temperature_6cm,soil_temperature_18cm,soil_temperature_54cm
 &daily=precipitation_sum,et0_fao_evapotranspiration&models=icon_seamless&forecast_days=7&past_days=7&timezone=UTC
```

## Variables, depth bands, units

All soil moisture values are **volumetric, m³/m³**. Soil temperature is in **°C**. Precipitation and ET₀ are in **mm** per day.

| API / model | Soil moisture variables (layer averages) | Soil temperature variables |
|---|---|---|
| Archive `era5_land` (0.1°, about 9 km), also `era5` (0.25°), `era5_seamless`, `best_match` | `soil_moisture_0_to_7cm`, `_7_to_28cm`, `_28_to_100cm`, `_100_to_255cm` | `soil_temperature_0_to_7cm`, `_7_to_28cm`, `_28_to_100cm`, `_100_to_255cm` (layer averages) |
| Forecast `icon_seamless`, `icon_d2`, `icon_eu`, `icon_global` (and `best_match` in DE) | `soil_moisture_0_to_1cm`, `_1_to_3cm`, `_3_to_9cm`, `_9_to_27cm`, `_27_to_81cm` | `soil_temperature_0cm`, `_6cm`, `_18cm`, `_54cm` (**point depths**, not layers) |
| Forecast `ecmwf_ifs025` (and `best_match`) | ERA5-style names `soil_moisture_0_to_7cm` … `_100_to_255cm` | ERA5-style `soil_temperature_0_to_7cm` … (`soil_temperature_0cm` is also available) |

The archive docs also list daily aggregates (`soil_moisture_0_to_7cm_mean`, `soil_moisture_0_to_100cm_mean`,
`soil_temperature_0_to_100cm_mean`, …). We did not use them; we computed our own daily means.

ICON forecast horizon per model (hours with non-null data, run of 2026-10-03):
`icon_d2` (2.2 km) about 55 h (until 2026-10-05 06:00), `icon_eu` (7 km) 121 h, `icon_global` (13 km) and `icon_seamless` the full 168 h.
`icon_seamless` blends D2, then EU, then Global, so the spatial resolution drops partway through the week.

## Time zone, latency, rate limits, licence

- **Time zone**: we always send `timezone=UTC` (the response says `"timezone":"GMT"`, `utc_offset_seconds:0`). Times are ISO strings without an offset.
  With `timezone=Europe/Berlin` or `auto`, the hourly stamps shift and **daily sums are aggregated over local days**,
  so `precipitation_sum` changes. Pick one time zone and keep it everywhere.
- **Archive latency**: on 2026-10-03 at about 09 UTC, the last non-null ERA5-Land/ERA5 hour was **2026-09-27T23:00**, a lag of about 5–6 days
  (the docs say "daily with 5 days delay"). The API does **not** error for newer dates. It returns `null`.
  `models=best_match` in the archive fills the gap with ECMWF IFS (9 km, different grid cell 52.197/9.963) up to today.
  To cover the gap, use the forecast API with `past_days=` (up to 92) for ICON.
- **Rate limits (free tier)**: <10,000 calls/day, <5,000/hour, <600/minute. Calls are **weighted**: >10 variables or >2 weeks
  per location count as fractional extra calls (2 weeks × 15 vars = 1.5 calls). One year × 8 vars × 1 location is about 26 weighted calls,
  so our full archive pull is about 210 weighted calls. A year per user request is affordable, but **cache it**.
- **Licence / commercial use**: data is **CC BY 4.0** (attribution to Open-Meteo plus the underlying sources: ECMWF/Copernicus ERA5-Land
  (Muñoz Sabater 2019), DWD ICON). The **free API is non-commercial only**. Commercial use, including "integrating our service into
  commercial products" and "undisclosed research at commercial entities", requires a paid subscription (API key, `customer-` URL prefix).
  A hackathon demo is fine. A product built on this needs a subscription, or self-hosting (the server is open source, AGPLv3).

## Grid cells: requested vs returned

| Site | requested (lat, lon) | ERA5-Land cell | dist km | ERA5 0.25° cell | ICON cell (dist km) | DEM elev / cell-mean elev m |
|---|---|---|---|---|---|---|
| Hildesheimer Börde | 52.22, 9.95 | 52.20, 10.00 | 4.1 | 52.25, 10.00 | 52.22, 9.96 (0.7) | 76 / 90 |
| Lüneburger Heide | 53.05, 10.05 | 53.10, 10.10 | 6.5 | 53.00, 10.00 | 53.04, 10.06 (1.3) | 99 / 96 |
| Emsland | 52.75, 7.35 | 52.80, 7.40 | 6.5 | 52.75, 7.25 | 52.76, 7.36 (1.3) | 35 / 22 |
| Wesermarsch | 53.35, 8.40 | 53.40, 8.40 | 5.6 | 53.25, 8.50 | 53.34, 8.40 (1.1) | 0 / −4 |
| Teufelsmoor | 53.25, 8.90 | 53.30, 8.90 | 5.6 | 53.25, 9.00 | 53.26, 8.90 (1.1) | 1 / 14 |
| Solling | 51.75, 9.55 | 51.80, 9.60 | 6.5 | 51.75, 9.50 | 51.76, 9.56 (1.3) | **520 / 299** |
| Hannover centre | 52.37, 9.73 | 52.40, 9.70 | 3.9 | 52.25, 9.75 | 52.36, 9.74 (1.3) | 56 / 48 |
| Hamburg | 53.55, 9.95 | 53.60, 10.00 | 6.5 | 53.50, 10.00 | 53.54, 9.96 (1.3) | 27 / 12 |

- Every site falls in its **own** ERA5-Land cell (no two sites share a cell). Cell centres are 4–6.5 km away (0.1° grid).
  Our sites sit exactly on x.x5° coordinates, which are cell **edges**, so the cell choice is a tie-break. A point 1 km away can flip to the neighbour cell.
- The default `cell_selection=land` returned the same cell as `nearest` for all 8 sites.
- `elevation` in the response is the **90 m DEM height of the requested point**, not the cell height. `&elevation=nan` returns the
  cell mean (Solling: 520 m point vs 299 m cell).
- **Soil temperature is elevation-downscaled; soil moisture is not.** Solling 2025-07-01 12 UTC: ST 0–7 cm 26.6 °C (default) vs
  28.0 °C (`elevation=nan`), and ST 100–255 cm 9.6 vs 11.1 °C. SM is identical (0.239). This is why Solling's mean ST is about 2 °C below the other sites.

## Per-site summary (ERA5-Land 2025, hourly, UTC)

SM = soil moisture m³/m³. P/ET₀ come from `era5_seamless` daily. SoilGrids FC = wv0033, WP = wv1500 (Q0.5), thickness-weighted onto the ERA5 band.

| Site | SM 0–7 cm min / median / max | SM 28–100 cm min / median / max | SM 100–255 median | ST 0–7 cm min / mean / max °C | P / ET₀ 2025 mm | SoilGrids FC / WP 28–100 | % hours SM > SG FC (28–100) |
|---|---|---|---|---|---|---|---|
| Hildesheimer Börde (loess) | 0.142 / 0.311 / 0.439 | 0.216 / 0.270 / 0.408 | 0.352 | −1.5 / 10.9 / 32.9 | 561 / 771 | n/a | n/a |
| Lüneburger Heide (sand) | 0.082 / 0.218 / 0.337 | 0.123 / 0.167 / 0.280 | 0.228 | −1.7 / 10.7 / 32.0 | 609 / 751 | 0.300 / 0.088 | 0 |
| Emsland (sand/peat) | 0.165 / 0.347 / 0.439 | 0.239 / 0.304 / 0.403 | 0.354 | −0.9 / 11.1 / 28.6 | 729 / 737 | 0.298 / 0.040 | 51 |
| Wesermarsch (marsh clay) | 0.170 / 0.353 / 0.430 | 0.283 / 0.328 / 0.412 | 0.362 | −0.8 / 10.8 / 27.2 | 738 / 706 | 0.282 / 0.127 | 100 |
| Teufelsmoor (bog) | 0.202 / 0.366 / 0.454 | 0.282 / 0.334 / 0.422 | 0.376 | −0.9 / 10.9 / 28.3 | 722 / 722 | 0.289 / 0.112 | 96 |
| Solling (upland forest) | 0.197 / 0.339 / 0.439 | 0.234 / 0.286 / 0.424 | 0.354 | −2.8 / 8.7 / 30.2 | 642 / 704 | 0.361 / 0.125 | 17 |
| Hannover centre (urban) | 0.158 / 0.309 / 0.439 | 0.204 / 0.263 / 0.405 | 0.347 | −1.3 / 11.2 / 32.6 | 564 / 778 | n/a | n/a |
| Hamburg | 0.074 / 0.227 / 0.346 | 0.130 / 0.179 / 0.288 | 0.237 | −2.0 / 10.6 / 30.8 | 657 / 710 | n/a | n/a |

SoilGrids n/a: Hannover has null values in `soilgrids_sites.csv`. Hamburg is not in that CSV. The Hildesheim row in that CSV was queried at
**52.12 N** (not 52.22) and is also null.

## Findings

**Seasonality.** Every site follows the same pattern: wet in Jan/Feb (SM near the site maximum), a dry-down from April, minima May–Sep,
and rewetting from Oct/Nov. The 0–7 cm band moves 0.24–0.30 m³/m³ over the year and responds to every rain event. 28–100 cm moves about 0.13–0.20 and
lags by weeks (its minimum is in Sep). 100–255 cm moves only about 0.06 and peaks in Feb. Soil temperature is damped and phase-lagged with depth.
At 100–255 cm the annual cycle is about 5→16 °C with its maximum in Sep/Oct.

**Sand vs clay/peat.** This partly works as expected. The two coarse cells, Lüneburger Heide (median 0–7 cm 0.218, max 0.337) and Hamburg
(0.227 / 0.346), are clearly drier than marsh clay (Wesermarsch 0.353) and bog (Teufelsmoor 0.366). It **fails for Emsland**: SoilGrids
says sand (WP 0.04), but the ERA5-Land cell behaves like the loess/marsh cells (median 0.347, max 0.439). The **bog does not behave like peat**: max 0.454,
whereas real peat holds >0.7 m³/m³. Wesermarsch clay is not distinguishable from the loess cell in range.

**Model field rather than site truth.** Four sites (Hildesheim, Emsland, Solling, Hannover) top out at exactly **0.439**, and the two sandy cells at
0.337/0.346. This is consistent with HTESSEL (ERA5-Land's land model) using a few per-soil-texture-class constants (dominant FAO texture class per cell):
the weather drives the dynamics, and only a handful of soil classes set the levels. Daily 0–7 cm SM correlates at 0.77–0.98 between sites, and
Hildesheim and Hannover (16 km apart) correlate at 0.98 (1.00 at 28–100 cm) with near-identical means (0.303 vs 0.305). Urban sealing is not represented.
**Treat ERA5-Land SM as a regional ~9 km signal of wetness and timing, not as site-specific absolute water content.**

**Comparison with SoilGrids FC/WP.** ERA5-Land SM never drops below SoilGrids WP (except 1.6 % of hours at 0–7 cm in the Heide).
For the marsh, the bog and the deep band, ERA5-Land sits **above** SoilGrids FC for most of the year (at 100–255 cm: 100 % of hours for Emsland, Wesermarsch and Teufelsmoor, 69 % for Solling, 0 % for the Heide).
This indicates that the two products use different water-retention parameterisations: ERA5-Land's soil-class constants are not SoilGrids' 33 kPa / 1500 kPa pedotransfer values. **Do not compute absolute
plant-available water by subtracting SoilGrids WP from ERA5 SM.** Instead, normalise ERA5 SM within its own range (e.g. percentile or
(SM − min)/(max − min) over a climatology), and use SoilGrids FC − WP × depth for the static *capacity*.

**Forecast vs archive.** At Hildesheim on 2026-09-26 12 UTC, ERA5-Land 0–7 cm = 0.231 and ICON 3–9 cm = 0.222, which is similar but comes from different models,
grids and soil parameters. Do not splice the two series without a bias offset.

## Gotchas

1. **`models=era5_land` returns `null` for `precipitation_sum`, `et0_fao_evapotranspiration` and hourly `precipitation`** (the HTTP status is still 200, with no error).
   Use `era5_seamless` (same ERA5-Land soil values plus ERA5 precipitation/ET₀) or `era5`.
2. Unsupported variable/model combinations do not error either. They return all-`null` with unit `"undefined"` (e.g. ICON variables on `ecmwf_ifs025`,
   ERA5 depth names on `icon_*`). Validate non-null counts.
3. Depth bands differ between APIs and models: ERA5 has 4 layers to 255 cm, ICON has 5 layers to 81 cm and temperature at **point** depths 0/6/18/54 cm.
   You need a harmonisation layer before serving "SM at depth X".
4. `best_match` silently changes model and grid (archive: ERA5-Land then IFS 9 km for recent days; forecast: ICON for ICON names, IFS for ERA5 names).
   Pin `models=` explicitly.
5. The archive lag is about 5 days and shows up as nulls, not as an error.
6. Multi-model requests suffix the variable names (`soil_moisture_0_to_1cm_icon_d2`). Multi-location requests return a list instead of an object.
7. Coordinates are returned as float32 (`52.199997`, `53.100006`). Round before comparing or using them as a cache key.
8. Soil temperature is elevation-downscaled (Solling −1.5 °C vs the cell). Soil moisture is not.

## How to use this in our API

- **Endpoint shape**: `GET /soil/{lon},{lat}/dynamics?from=&to=` returns, per ERA5 band, the hourly or daily SM/ST series, plus daily P/ET₀.
  Also return `GET /soil/{lon},{lat}/forecast`, the ICON 7-day SM/ST in ICON's native bands (labelled as such).
- **Backend calls**: one `archive` call with `models=era5_seamless&timezone=UTC` (hourly soil + daily P/ET₀) for history, and one `forecast` call with
  `models=icon_seamless&past_days=7&forecast_days=7` to bridge the 5-day lag and give the outlook. Batch locations with comma lists.
- **Caching**: key on the returned ERA5-Land cell (0.1° grid, rounded), not on the request point. Every point inside the same cell gets identical SM,
  so cache per cell and per day. Past ERA5-Land data is immutable once published, so it can be cached indefinitely. Refresh forecasts per ICON run (every 3 h for D2, 6 h otherwise).
- **Combining with SoilGrids/BÜK (static)**:
  - static: texture, bulk density, FC (wv0033), WP (wv1500), so available water capacity per horizon = (FC − WP) × thickness.
  - dynamic: ERA5-Land gives the *relative* wetness state (percentile of the cell's climatology), timing of dry-downs and rewetting, frost depth/soil
    temperature (e.g. ST 0–7 cm > 8–10 °C for sowing), and the P − ET₀ balance.
  - A combined "current fill level" = relative wetness (ERA5, normalised in its own range) × static capacity (SoilGrids/BÜK), flagged as a
    model estimate at about 9 km resolution.
- Always return `grid_cell_lat/lon`, `model`, `distance_km` and `data_until` (last non-null timestamp) with the values. Add attribution
  ("Weather data by Open-Meteo.com, ERA5-Land (Copernicus/ECMWF), DWD ICON", CC BY 4.0).
