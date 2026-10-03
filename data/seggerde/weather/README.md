# Seggerde farm weather, 2019 → latest

Daily weather and soil moisture from Open-Meteo's ERA5 archive (`models=era5_seamless`), matching the Sentinel-2 history in `../sentinel2/`.

```
uv run fetch_weather.py      # one request, a few seconds; raw response cached in raw/
```

## Why 4 points, not 87

All 87 fields fall in **4 ERA5 cells** (~9 km grid, see `../openmeteo_fields.csv`), so the script requests the 4 cell centres. `field_cell.csv` maps each `plotId` to its cell; join on it to get a field's weather.

Fields per cell: 34, 27, 25 and 1.

## Files

| File | Rows | Content |
|---|---|---|
| `daily.csv` | 4 cells × 2,832 days | precipitation, rain, ET₀ (FAO), mean/max/min temperature, shortwave radiation, daily-mean soil moisture 0–7 / 7–28 / 28–100 cm |
| `seasons.csv` | 4 cells × 8 years | growing-season indicators (below) |
| `field_cell.csv` | 87 | plotId → cell |
| `raw/archive_*.json` | | untouched response |

Time zone is Europe/Berlin. Data ends **2026-09-27** (ERA5 archive lag ~6 days); the last days of the request are null, which is all of the 0.2 % nulls. `season_complete` is false for 2026, whose March–October season isn't over.

### Season indicators (`seasons.csv`)

| Column | Meaning |
|---|---|
| `precip_MarOct_mm`, `et0_MarOct_mm` | Totals over March–October |
| `cwb_MarOct_mm` | Climatic water balance = precipitation − ET₀ (negative = deficit) |
| `precip_AprJun_mm`, `cwb_AprJun_mm` | Spring, the critical window for cereals |
| `gdd5_MarOct` | Growing degree days above 5 °C |
| `hot_days_tmax30` | Days with max ≥ 30 °C |
| `frost_days_AprMay` | Days with min < 0 °C in April–May |
| `longest_dry_spell_MarOct_d` | Longest run of days with < 1 mm |
| `sm7_28_MayJul_mean/min`, `sm28_100_MayJul_mean` | ERA5-Land soil moisture, m³/m³ |
| `radiation_MarOct_MJ` | Shortwave radiation total |

## Farm-wide by year (mean of the 4 cells)

| Year | Rain Mar–Oct (mm) | Water balance Mar–Oct (mm) | Water balance Apr–Jun (mm) | Days ≥ 30 °C | Longest dry spell (d) | Farm peak NDVI |
|---|---|---|---|---|---|---|
| 2019 | 439 | −297 | −167 | 12 | 14 | 0.855 |
| 2020 | 412 | −297 | −177 | 6 | 24 | 0.843 |
| 2021 | 501 | −119 | −57 | 3 | 13 | 0.862 |
| 2022 | 348 | −389 | −211 | 7 | 21 | 0.818 |
| 2023 | 527 | −170 | −179 | 5 | 14 | 0.854 |
| 2024 | 561 | −145 | −66 | 5 | 12 | 0.843 |
| 2025 | 375 | −339 | −194 | 6 | 25 | 0.804 |
| 2026* | 303 | −374 | −142 | 13 | 14 | 0.866 |

\* Up to 2026-09-27. Farm peak NDVI = median over fields of the peak-season NDVI (`../sentinel2/field_season_peaks.csv`), computed per field with that field's cell.

## Findings

- **Water is the limiting factor.** Every season has a deficit (ET₀ exceeds rain). Peak NDVI tracks the water balance: Spearman ρ = 0.77 for March–October and 0.76 for April–June (n = 7 complete seasons, p ≈ 0.05). The driest years, 2022 and 2025, have the lowest peaks. Seven seasons is a small sample, so treat this as a strong hint, not a model.
- **Heat days don't explain the variation** (ρ = −0.27).
- **2026 is odd:** very dry overall but with the highest peak NDVI. A wetter spring than 2022/2025 (−142 mm) may explain it, or a different crop mix. Without crop history we can't tell.
- **The 4 cells barely differ.** Seasonal rain differs between cells by 18–55 mm per year, and soil moisture by ≤ 0.03 m³/m³. Weather is a farm-level signal here, not a field-level one.

## How to use it

- **Normalise NDVI by year.** Because year-to-year NDVI swings with water supply, compare fields within a year (relative productivity, as `../sentinel2/` already does) rather than across years.
- **Explain the zones.** If stable-low zones get worse in dry years, they are likely water-limited (sandy soil or high ground). That can be checked by combining zones with BÜK200 units and the DEM.
- **14-day refresh:** re-run the script; it fetches through yesterday and the archive fills in with a ~6-day lag. Use the Open-Meteo forecast (ICON) for the newest days.
