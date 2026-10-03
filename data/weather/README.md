# ERA5-Land daily weather (legacy ingest)

| | |
|---|---|
| **id** | `weather` |
| **status** | `legacy` |
| **kind** | legacy |
| **working CRS** | 0.1° cells; Open-Meteo / Earth Engine backends |
| **license** | CC BY 4.0 (Open-Meteo path) / Copernicus C3S (ERA5-Land) |
| **citation** | See open_meteo pack for preferred ERA5-Land citation |

## Layers / outputs

daily weather parquet by cell → interim/weather_daily.parquet

## Our changes / notes

- Cell-key cache; trim incomplete trailing days
- Superseded for soil moisture layers by tunen/adapters/open_meteo.py

## Caveats

Legacy; prefer open_meteo adapter for soil moisture / temperature / CWB.

## Local cache (not shipped)

`data/raw/weather/<cell>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
