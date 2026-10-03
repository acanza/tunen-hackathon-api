# How to download / regenerate — `smap_l4`

## Commands (local working tree)

```bash
python -m tools.review_sources --sources smap_l4
# Requires AppEEARS / Earthdata credentials via environment variables
```

## Config

smap_l4 section in config.yaml; never put API keys in code

## Cache location

`data/cache/smap_l4/<cell_key>/`

Do not commit cache contents. This pack only documents the source and may include small sample figures under `output/`.
