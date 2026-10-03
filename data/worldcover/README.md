# ESA WorldCover 2021 (legacy ingest)

| | |
|---|---|
| **id** | `worldcover` |
| **status** | `legacy` |
| **kind** | legacy |
| **working CRS** | Parcel zonal stats on ESA WC tiles |
| **license** | CC BY 4.0 (ESA WorldCover) |
| **citation** | Zanaga et al. (2022), ESA WorldCover 10 m 2021 v200 |

## Layers / outputs

cropland fraction / is_cropland flag

## Our changes / notes

- Cropland class fraction per parcel
- Spec: low cropland → flag, not hard reject (see docs; runner may still reject — track in working tree)

## Caveats

Input filter / land-use context, not a soil property.

## Local cache (not shipped)

`data/raw/worldcover/<parcel_id>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
