# Data sources

GitHub-facing packs for each Tunen data source. Layout per source:

```
data/<source>/
  README.md      # what, license, our changes
  download.md    # how to fetch / regenerate
  script/        # pointer to adapter or legacy module
  output/        # small sample figures only (no review_*.md, no caches)
```

Reference tables remain in [`data/ref/`](ref/).

Status: `ready` = reviewed sample figures available · `wip` = adapter/docs · `legacy` = older `tunen_ingest/sources` path.

| Source | Status | Title | Caveat |
|---|---|---|---|
| [`open_meteo`](open_meteo/) | `ready` | Open-Meteo ERA5-Land | ERA5-Land ~9 km: uniform within a field; signal is in the time dimension. |
| [`copernicus_dem`](copernicus_dem/) | `ready` | Copernicus DEM GLO-30 | Surface model: hedges/trees inflate edge slopes. Prefer LGLN DGM1 inside Niedersachsen when available. |
| [`buek200`](buek200/) | `wip` | BGR BÜK200 | National 1:200k soil map — coarse for small parcels; texture ranges from legend lookup. |
| [`lgln_dgm1`](lgln_dgm1/) | `wip` | LGLN DGM1 (Niedersachsen) | Coverage is Niedersachsen only. Outside envelope → empty / fallback. |
| [`lbeg_bk50`](lbeg_bk50/) | `wip` | LBEG BK50 (nFKWe + BOTYP) | Niedersachsen WMS; licence/citation still TODO in code. |
| [`lbeg_bodenschaetzung`](lbeg_bodenschaetzung/) | `wip` | LBEG Bodenschätzung (BS5) | Applicable mainly on cropland; licence/citation TODO. |
| [`smap_l4`](smap_l4/) | `wip` | SMAP L4 SPL4SMGP (AppEEARS) | Coarse resolution; needs Earthdata login. Citation DOI marked TODO in code. |
| [`guek200`](guek200/) | `wip` | BGR GÜK200 (geology covariate) | Not a soil-property source. Do not fuse as clay/SOC/pH. |
| [`soilgrids`](soilgrids/) | `legacy` | SoilGrids 2.0 (legacy ingest) | Legacy pipeline module; newer fusion prefers Länder / BÜK where available. |
| [`worldcover`](worldcover/) | `legacy` | ESA WorldCover 2021 (legacy ingest) | Input filter / land-use context, not a soil property. |
| [`sentinel2`](sentinel2/) | `legacy` | Sentinel-2 L2A NDVI (legacy ingest) | Often disabled in config for soil-first runs. Do not change scale_offset without tests. |
| [`weather`](weather/) | `legacy` | ERA5-Land daily weather (legacy ingest) | Legacy; prefer open_meteo adapter for soil moisture / temperature / CWB. |
| [`dem`](dem/) | `legacy` | Copernicus DEM fetch (legacy ingest) | Legacy twin of copernicus_dem adapter. |

## Rules

- Do **not** commit `review_*.md` QA reports.
- Do **not** commit `data/*/cache/`, `data/*/raw/`, GeoTIFF/NetCDF dumps, or parcel `outputs/`.
- Licenses/citations must match code/`config.yaml`; keep TODO when unverified.
