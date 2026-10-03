# SoilGrids rasters for the Seggerde farm

Analysis-ready SoilGrids v2.0 rasters, built by `soilgrids_rasters.py` from ISRIC's WCS.

```
uv run soilgrids_rasters.py                       # farm area (from ../sentinel2/grid_and_params.json)
uv run soilgrids_rasters.py 9.9 52.1 10.1 52.3    # any lon/lat bbox: west south east north (utm250 only)
```

Runs in a few minutes (395 WCS requests, ~0.4 s each); downloads are cached in `raw/`.

## Files

| Folder | Grid | Use it for |
|---|---|---|
| `utm250/<prop>.tif` | EPSG:32632, 250 m, 38 × 32 cells | Honest resolution: map display, per-field area-weighted stats |
| `s2grid/<prop>.tif` | EPSG:32632, 10 m, 894 × 728, **identical to the Sentinel-2 grid** | Stacking with NDVI pixel-for-pixel (e.g. yield-potential model inputs) |
| `raw/<prop>_<depth>_<stat>.tif` | Homolosine, 250 m, integer, no CRS, 0 = nodata | Source of truth as returned by the WCS |
| `summary.json` | | Bands, nodata share, topsoil median range per property |

`s2grid` values are **still 250 m data**: each SoilGrids cell is repeated (nearest neighbour), not refined. Don't read field-scale patterns into it.

## Bands

One file per property: `bdod cec cfvo clay sand silt nitrogen ocd phh2o soc wv0010 wv0033 wv1500` (30 bands each) and `ocs` (5 bands, 0–30 cm only).

Bands are named `<depth>_<stat>` (band descriptions in the GeoTIFF), ordered depth-major:
`0-5cm_Q0.05, 0-5cm_Q0.5, 0-5cm_Q0.95, 0-5cm_mean, 0-5cm_uncertainty, 5-15cm_Q0.05, …, 100-200cm_uncertainty`.

- Values are in display units (raw ÷ d_factor). The unit is in the file's `unit` tag: % for texture, pH, g/kg for SOC and nitrogen, g/cm³ for bulk density, cmol(c)/kg for CEC, vol % for coarse fragments and water content, kg/m³ for `ocd`, kg/m² for `ocs`.
- `uncertainty` bands = (Q0.95 − Q0.05) / Q0.5, unitless.
- Nodata = NaN. About 2.2 % of the area has no prediction.

Reading a band by name:

```python
import rasterio
with rasterio.open("s2grid/clay.tif") as src:
    clay = src.read(src.descriptions.index("0-5cm_Q0.5") + 1)
```

## Values over the farm area (topsoil 0–5 cm, median)

| Property | Range |
|---|---|
| clay | 4.1–19.1 % |
| sand | 47.2–70.8 % |
| pH | 4.2–7.4 |
| SOC | 17.4–48.6 g/kg |
| wv0033 (field capacity) | 35.2–39.0 vol % |
| wv1500 (wilting point) | 8.0–14.6 vol % |

The area is a little larger than the fields themselves, so the ranges are wider than the per-field numbers in `../README.md`.
