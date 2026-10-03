# How to download / regenerate — `weather`

## Commands (local working tree)

```bash
python -m tunen_ingest.run --sources weather --parcels examples/sample_parcels.geojson --start 2023-01-01 --end 2024-12-31 --limit 3
```

## Config

sources.weather (often false when using open_meteo adapter)

## Cache location

`data/raw/weather/<cell>/`

Do not commit cache contents. This pack only documents the source and may include small sample figures under `output/`.
