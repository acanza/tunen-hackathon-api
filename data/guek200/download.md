# How to download / regenerate — `guek200`

## Commands (local working tree)

```bash
python -m ingest.guek  # or via tools/run_all pipeline
# Layer IDs from tools/probe_arcgis.py (2026-10-03)
```

## Config

sources.guek200; guek200 section + data/ref/guek_lithology_groups.csv

## Cache location

`writes data/features/geology.parquet (local working tree)`

Do not commit cache contents. This pack only documents the source and may include small sample figures under `output/`.
