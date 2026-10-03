# Soil data exploration

Exploratory pulls of each source listed in `../dataset.md`, so we can decide how to combine them in the API.
Each source has its own folder with a fetch script, the pulled data (raw responses where kept) and a detailed README.

| Source | Folder | What it gives | Coverage |
|---|---|---|---|
| ISRIC SoilGrids v2.0 | [`soilgrids_eda/`](soilgrids_eda/README.md) | Numeric soil properties (clay, pH, SOC, water retention…) at 6 depths, with 5–95 % interval and uncertainty | Global, 250 m, gaps on some land |
| LBEG BK50 + Bodenschätzung (NIBIS) | [`nibis_eda/`](nibis_eda/README.md) | Soil type, plant-available water (nFKWe), groundwater class, peat thickness, Bodenzahl/Ackerzahl | Niedersachsen only, 1:50k / 1:5k |
| BGR BÜK200 | [`buek200_eda/`](buek200_eda/README.md) | Soil unit and reference profiles with horizons (KA5 classes) | All of Germany, 1:200k |
| Open-Meteo (ERA5-Land + DWD ICON) | [`openmeteo_eda/`](openmeteo_eda/README.md) | Soil moisture and temperature over time, precipitation, ET₀, 7-day forecast | Global / Europe, ~9 km model grid |
| Copernicus DEM GLO-30 | [`dem_eda/`](dem_eda/README.md) | Elevation, slope, aspect | Global, 30 m (surface model) |

**Real farm:** [`seggerde/`](seggerde/README.md) runs every source against the 87 active fields of `../LuF-Seggerde-Dev-fields.geojson` and lists coverage and missing values per field (`field_coverage.csv`).

`9.950_53.550/` holds single-point sample responses for Hamburg centre, not part of these pulls.

## Test sites

All folders use the same coordinates so results can be joined by `lon, lat`.
Site names are our own labels for the landscape, not data from any source.

| Site | lon | lat | Why it's included |
|---|---|---|---|
| Hildesheimer Börde (loess) | 9.95 | 52.22 | Fertile loess farmland |
| Hildesheim edge | 9.95 | 52.12 | Farmland where SoilGrids returns null (first Börde guess) |
| Lüneburger Heide (sand) | 10.05 | 53.05 | Sandy soils |
| Emsland (sand/peat) | 7.35 | 52.75 | Sand and peat |
| Wesermarsch (marsh clay) | 8.40 | 53.35 | Marsh clay |
| Teufelsmoor (bog) | 8.90 | 53.25 | Bog |
| Solling (upland forest) | 9.55 | 51.75 | Upland forest |
| Hannover centre (urban) | 9.73 | 52.37 | Urban control |
| Farmland, SoilGrids null | 10.10 | 52.18 | Farmland where SoilGrids returns null |
| Hamburg | 9.95 | 53.55 | Outside Niedersachsen, urban |

Not every source was pulled for every site: SoilGrids used 7 sites (Börde at `9.95, 52.12`, no Hamburg), DEM and Open-Meteo used 8 (no Hildesheim edge, no `10.10, 52.18`).

## Sources side by side

### What each source says per site

| Site | SoilGrids (topsoil, mean) | BK50 soil type (LBEG) | Bodenzahl / Ackerzahl | nFKWe (mm) | BÜK200 unit | DEM elevation (m) |
|---|---|---|---|---|---|---|
| Hildesheimer Börde | clay 11.8 %, SOC 19.9 g/kg (median, `9.95, 52.22`) | Tschernosem-Parabraunerde | 71 / 74 (lS3Lo) | 228 | Pseudogley-Tschernosem on loess | 76.7 |
| Hildesheim edge | **null** | Pseudogley-Parabraunerde | – | 225 | Parabraunerden / Pseudogleye | – |
| Farmland 10.10/52.18 | **null** | Pseudogley-Tschernosem | 90 / 94 (L2Lo) | 228 | Pseudogley-Tschernosem | – |
| Lüneburger Heide | clay 8 %, sand 71 % | Braunerde-Podsol | forest | 126 | Braunerde-Podsole on sand | 98.2 |
| Emsland | clay 6 %, sand 82 % | Gley-Podsol | forest | 193 | Braunerde-/Gley-Podsole | 28.0 |
| Wesermarsch | clay 30 % | Kalkmarsch | 84 / 84 (LI-) | 139 | Kalkmarschen | −0.4 |
| Teufelsmoor | clay 36 % ⚠ | Erdhochmoor, 160 cm peat | 37 / 37 (MoII-) | 225 | Hochmoore | 0.6 |
| Solling | clay 26 % | podsolierte Braunerde | forest | 129 | Braunerden | 512.6 |
| Hannover centre | **null** | made ground, values null | – | – | Stadtkernbereiche (urban) | 56.0 |
| Hamburg | **null** | no coverage (outside NI) | – | – | Stadtkernbereiche (urban) | 31.1 |

"forest" = no Bodenschätzung, which only covers agricultural land. ⚠ = SoilGrids reports mineral clay where BK50 and BÜK200 both say peat.

### What the comparison shows

1. **SoilGrids has gaps on farmland, not only in cities.** Both farmland points it returns null for have full BK50 and BÜK200 data.
2. **SoilGrids misses peat.** At Teufelsmoor it reports 36 % clay; BK50 says 160 cm of peat, BÜK200 says raised bog.
3. **BK50 and BÜK200 agree** on the soil type at every site, at different levels of detail. BK50 adds numbers (nFKWe, groundwater class, peat thickness, Bodenzahl); BÜK200 adds horizon descriptions.
4. **Only SoilGrids gives numeric texture and an uncertainty.** BK50 via WMS has no clay %; BÜK200 gives KA5 texture classes (e.g. `Ut3`), not percentages.
5. **Open-Meteo is a smooth ~9 km model field.** It shows seasons well but not site differences (bog moisture never above 0.45; Hannover looks like nearby farmland). Its moisture values often sit above SoilGrids' field capacity, so use it for relative wetness, not absolute water.
6. **The DEM includes trees and buildings.** Raw slope is unreliable at 5 of 8 sites; use the smoothed slope and the `dsm_artifact_suspect` flag.

### Which source to use for what

| Need | Inside Niedersachsen | Elsewhere in Germany | Fallback |
|---|---|---|---|
| Soil type | BK50 | BÜK200 | SoilGrids (no type, only properties) |
| Plant-available water | BK50 nFKWe | SoilGrids `wv0033 − wv1500` | – |
| Productivity score | Bodenzahl / Ackerzahl (farmland only) | – | – |
| Clay / sand / silt % | SoilGrids (check against BK50 Klassenzeichen) | SoilGrids (check against BÜK200 KA5 class) | – |
| pH, SOC, CEC, bulk density | SoilGrids | SoilGrids | BÜK200 humus class |
| Peat, groundwater | BK50 | BÜK200 | – |
| Uncertainty / confidence | SoilGrids interval | SoilGrids interval | – |
| Moisture and temperature over time | Open-Meteo | Open-Meteo | – |
| Terrain | Copernicus DEM | Copernicus DEM | – |

## Access cheat sheet

| Source | Calls per point | Latency | Key gotchas |
|---|---|---|---|
| SoilGrids | 3 (5 properties each) | 30–45 s each | Slow; ~5 req/min fair use; cache by coordinate; use median not mean |
| NIBIS (BK50 + Bodenschätzung) | 1 per layer | ~0.3 s | 10 m BBOX in EPSG:25832; encode `geo+json` as `geo%2Bjson`; ~2.5 % of requests hang, retry with 3–5 s timeout; units not in response |
| BÜK200 | 2–3 | ~0.3–0.5 s each | Find map sheet first; horizons only as HTML; use `/query` not `/identify`; classes not numbers |
| Open-Meteo | 1 (many sites per call) | ~10 s for 8 sites × 1 year | Use `models=era5_seamless`; archive lags ~5–6 days; forecast uses different depth bands; free tier non-commercial |
| Copernicus DEM | 1 tile open + window read | 0.3–0.5 s, 1–3 MB | Surface model; build tile URL from coordinates; tile edges not handled |

Licences: SoilGrids CC BY 4.0, Open-Meteo data CC BY 4.0 (free API non-commercial). BK50 and BÜK200 licence terms were not verified.

## Running the scripts

Python dependencies are declared inline in each script, so run them with `uv`, from inside the script's folder:

```
cd data/soilgrids_eda && uv run fetch.py
```
