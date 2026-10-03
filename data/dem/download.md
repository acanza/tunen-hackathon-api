# How to download / regenerate — `dem`

## Commands (local working tree)

```bash
python -m tunen_ingest.run --sources dem --parcels examples/sample_parcels.geojson --start 2023-01-01 --end 2024-12-31 --limit 3
```

## Config

sources.dem

## Cache location

`data/raw/dem/<parcel_id>/`

Do not commit cache contents. This pack only documents the source and may include small sample figures under `output/`.
