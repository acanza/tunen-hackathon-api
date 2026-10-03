# BGR BÜK200

| | |
|---|---|
| **id** | `buek200` |
| **status** | `wip` |
| **kind** | adapter |
| **working CRS** | EPSG:25832 field grid; source ArcGIS REST (BGR) |
| **license** | TODO: verify BGR Geodaten Nutzungsbestimmungen |
| **citation** | BÜK200, (C) BGR, Hannover |

## Layers / outputs

soil_unit, soil_type, parent_material, is_peat, clay_pct, silt_pct, sand_pct

## Our changes / notes

- Texture via lookup tables in data/ref (not hard-coded)
- Peat flag from map units; sheet-based cache by geometry hash

## Caveats

National 1:200k soil map — coarse for small parcels; texture ranges from legend lookup.

## Local cache (not shipped)

`data/cache/buek200/<geom_hash>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
