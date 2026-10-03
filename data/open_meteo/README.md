# Open-Meteo ERA5-Land

| | |
|---|---|
| **id** | `open_meteo` |
| **status** | `ready` |
| **kind** | adapter |
| **working CRS** | Field grid EPSG:25832 (values spatially uniform at ~9 km ERA5-Land cell) |
| **license** | CC BY 4.0 |
| **citation** | Weather data by Open-Meteo.com; Muñoz Sabater, J. (2019): ERA5-Land hourly data from 1950 to present. Copernicus C3S CDS. |

## Layers / outputs

soil_moisture (m³/m³), soil_moisture_pctl (%), soil_temperature (°C), water_balance_30d (mm); optional soil_moisture_forecast

## Our changes / notes

- 0–30 cm soil moisture / temperature depth weighting from ERA5-Land layers
- Climatological percentile (DOY ±15) and 30-day climatic water balance
- Optional ICON forecast path kept separate from archive
- Agreement JSON with SMAP when present in cache

## Caveats

ERA5-Land ~9 km: uniform within a field; signal is in the time dimension.

## Local cache (not shipped)

`data/cache/open_meteo/<cell_key>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
