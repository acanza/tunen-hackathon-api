# SMAP L4 SPL4SMGP (AppEEARS)

| | |
|---|---|
| **id** | `smap_l4` |
| **status** | `wip` |
| **kind** | adapter |
| **working CRS** | Field grid EPSG:25832 (values uniform at SMAP cell) |
| **license** | NASA open data |
| **citation** | TODO: verify — SMAP L4 SPL4SMGP.008; DOI: 10.5067/T5RUATAQREF8 |

## Layers / outputs

soil_moisture_surface, soil_moisture_rootzone (m³/m³)

## Our changes / notes

- Daily cache by cell key; agreement helper used by open_meteo

## Caveats

Coarse resolution; needs Earthdata login. Citation DOI marked TODO in code.

## Local cache (not shipped)

`data/cache/smap_l4/<cell_key>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
