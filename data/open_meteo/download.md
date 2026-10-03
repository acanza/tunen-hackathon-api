# How to download / regenerate — `open_meteo`

## Commands (local working tree)

```bash
python -m tools.review_sources --sources open_meteo
# or via pipeline / adapter REGISTRY key: open_meteo
```

## Config

sources switches and open_meteo section in config.yaml (working tree)

## Cache location

`data/cache/open_meteo/<cell_key>/`

Do not commit cache contents. This pack only documents the source and may include small sample figures under `output/`.
