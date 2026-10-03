# LGLN DGM1 (Niedersachsen)

| | |
|---|---|
| **id** | `lgln_dgm1` |
| **status** | `wip` |
| **kind** | adapter |
| **working CRS** | EPSG:25832; WCS coverage ni_dgm1 (Niedersachsen only) |
| **license** | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| **citation** | © GeoBasis-DE / LGLN <year> (TODO: verify exact attribution text) |

## Layers / outputs

elevation, relative_elevation, slope, aspect, twi, relative_elevation_1m

## Our changes / notes

- 1 m DTM via WCS; TWI and relative elevation on 10 m field grid
- Separate 1 m relative_elevation_1m layer
- Fallback to Copernicus GLO-30 outside coverage (pipeline-level)

## Caveats

Coverage is Niedersachsen only. Outside envelope → empty / fallback.

## Local cache (not shipped)

`data/cache/lgln_dgm1/<geom_hash>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
