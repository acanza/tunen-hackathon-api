# Copernicus DEM GLO-30

| | |
|---|---|
| **id** | `copernicus_dem` |
| **status** | `ready` |
| **kind** | adapter |
| **working CRS** | EPSG:25832 field grid; source tiles via Earth Search / AWS COGs |
| **license** | COPERNICUS / proprietary (TODO: verify official wording) |
| **citation** | © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA (TODO: verify) |

## Layers / outputs

elevation (m), slope (%), aspect (deg)

## Our changes / notes

- Slope/aspect derived on the parcel field grid
- Interior mask applied; surface model (DSM) — vegetation/edges can inflate slope

## Caveats

Surface model: hedges/trees inflate edge slopes. Prefer LGLN DGM1 inside Niedersachsen when available.

## Local cache (not shipped)

`data/raw/dem/<parcel_id>/ (legacy ingest) / adapter runtime cache as configured`

Large caches and parcel rasters stay in the local working tree and are gitignored.
