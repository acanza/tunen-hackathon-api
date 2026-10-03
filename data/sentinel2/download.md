# How to download / regenerate — `sentinel2`

## Commands (local working tree)

```bash
python -m tunen_ingest.run --sources s2 --parcels examples/sample_parcels.geojson --start 2023-01-01 --end 2024-12-31 --limit 3
```

## Config

sources.sentinel2_timeseries; sentinel2.scale_offset (-1000 DN from baseline 04.00)

## Cache location

`data/raw/sentinel2/<parcel_id>/`

Do not commit cache contents. This pack only documents the source and may include small sample figures under `output/`.
