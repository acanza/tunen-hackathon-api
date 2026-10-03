# LBEG Bodenschätzung (BS5)

| | |
|---|---|
| **id** | `lbeg_bodenschaetzung` |
| **status** | `wip` |
| **kind** | adapter |
| **working CRS** | EPSG:25832; LBEG NIBIS WMS PkgId=24 |
| **license** | TODO: verify |
| **citation** | TODO: verify — LBEG NIBIS Bodenkarten WMS (PkgId=24) |

## Layers / outputs

bodenzahl, ackerzahl, bodenart_class, land_use_type

## Our changes / notes

- Bodenzahl / Ackerzahl / Bodenart from BS5 WMS layers
- Bodenart groups via data/ref lookup

## Caveats

Applicable mainly on cropland; licence/citation TODO.

## Local cache (not shipped)

`data/cache/lbeg/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
