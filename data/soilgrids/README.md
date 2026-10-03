# SoilGrids 2.0 (legacy ingest)

| | |
|---|---|
| **id** | `soilgrids` |
| **status** | `legacy` |
| **kind** | legacy |
| **working CRS** | Parcel stats; ISRIC VRT mean layers |
| **license** | CC-BY 4.0 (ISRIC SoilGrids) — confirm with ISRIC terms |
| **citation** | Poggio et al. (2021), SoilGrids 2.0, SOIL 7: 217-240 |

## Layers / outputs

clay/silt/sand, SOC, pH (depth bands) → interim/soil.parquet

## Our changes / notes

- Only mean bands; unit conversions via CONVERSION table
- Optional Saxton–Rawls nFK helper (citation in code)

## Caveats

Legacy pipeline module; newer fusion prefers Länder / BÜK where available.

## Local cache (not shipped)

`data/raw/soilgrids/<parcel_id>/`

Large caches and parcel rasters stay in the local working tree and are gitignored.
