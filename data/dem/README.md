# Copernicus DEM fetch (legacy ingest)

| | |
|---|---|
| **id** | `dem` |
| **status** | `legacy` |
| **kind** | legacy |
| **working CRS** | Parcel UTM; Copernicus DEM GLO-30 |
| **license** | See copernicus_dem pack (TODO verify) |
| **citation** | See copernicus_dem pack |

## Layers / outputs

dem.nc on parcel UTM grid

## Our changes / notes

- Legacy NetCDF write path
- Prefer tunen/adapters/copernicus_dem.py + lgln_dgm1 for new pipeline

## Caveats

Legacy twin of copernicus_dem adapter.

## Local cache (not shipped)

`data/raw/dem/<parcel_id>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
