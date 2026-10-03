# LBEG BK50 (nFKWe + BOTYP)

| | |
|---|---|
| **id** | `lbeg_bk50` |
| **status** | `wip` |
| **kind** | adapter |
| **working CRS** | EPSG:25832; LBEG NIBIS WMS PkgId=24 |
| **license** | TODO: verify |
| **citation** | TODO: verify — LBEG NIBIS Bodenkarten WMS (PkgId=24) |

## Layers / outputs

nfk_mm (mm), soil_type_bk50 (code)

## Our changes / notes

- Layers discovered via GetCapabilities (not guessed)
- nFKWe class → mm via data/ref/bk50_nfkwe_classes.csv

## Caveats

Niedersachsen WMS; licence/citation still TODO in code.

## Local cache (not shipped)

`data/cache/lbeg/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
