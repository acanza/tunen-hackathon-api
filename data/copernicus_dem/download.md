# How to download / regenerate — `copernicus_dem`

## Commands (local working tree)

```bash
python -m tools.review_sources --sources copernicus_dem
# CLI helper: python -m tunen.cli_dem (working tree)
```

## Config

sources.dem / sources.lgln_dgm1; DEM settings in config.yaml

## Cache location

`data/raw/dem/<parcel_id>/ (legacy ingest) / adapter runtime cache as configured`

Do not commit cache contents. This pack only documents the source and may include small sample figures under `output/`.
