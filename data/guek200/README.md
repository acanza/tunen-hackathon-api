# BGR GÜK200 (geology covariate)

| | |
|---|---|
| **id** | `guek200` |
| **status** | `wip` |
| **kind** | ingest |
| **working CRS** | Query in EPSG:25832; service native 3857 |
| **license** | Nutzungsbestimmungen für die Bereitstellung von Geodaten des Bundes |
| **citation** | GÜK200, (C) BGR, Hannover, 2026 |

## Layers / outputs

geology.parquet features: unit_code, unit_desc, lithology, age, grupo, area_fraction (not soil properties)

## Our changes / notes

- ArcGIS REST MapServer layer 4 (Flächen) after GetCapabilities/probe
- Never written to source_values — map context / Level-B covariate only

## Caveats

Not a soil-property source. Do not fuse as clay/SOC/pH.

## Local cache (not shipped)

`writes data/features/geology.parquet (local working tree)`

Large caches and parcel rasters stay in the local working tree and are gitignored.
