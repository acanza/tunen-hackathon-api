# Sentinel-2 L2A NDVI (legacy ingest)

| | |
|---|---|
| **id** | `sentinel2` |
| **status** | `legacy` |
| **kind** | legacy |
| **working CRS** | UTM window per parcel; STAC search |
| **license** | ESA Copernicus Sentinel open data |
| **citation** | Copernicus Sentinel-2 (ESA) |

## Layers / outputs

NDVI time series + SCL mask summary → interim/s2_timeseries.parquet

## Our changes / notes

- Delicate: scale_offset -1000 DN (baseline 04.00, Jan 2022) — tests must pass if changed
- Cloud mask: SCL classes 4 and 5 only
- Interior buffer -10 m before statistics

## Caveats

Often disabled in config for soil-first runs. Do not change scale_offset without tests.

## Local cache (not shipped)

`data/raw/sentinel2/<parcel_id>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
