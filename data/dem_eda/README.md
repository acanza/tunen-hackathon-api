# Copernicus DEM GLO-30: EDA for point terrain attributes

Source: Copernicus DEM GLO-30 Public (TanDEM-X, 1 arc-second **DSM**, "2021-04-22" release), hosted as
public Cloud-Optimized GeoTIFFs on AWS (`s3://copernicus-dem-30m/`, eu-central-1, no credentials, not requester-pays).

Status: **works**. All 8 test sites returned values. Each point costs one ~1–3.4 MB HTTP range read and about 0.3–0.6 s cold, or about 0 ms when the block is already cached.

## Files

| file | content |
|---|---|
| `fetch.py` | Reproducible script (`uv run data/dem_eda/fetch.py`; PEP 723 deps: rasterio, numpy, pystac-client) |
| `dem_sites.csv` | Per-site results (one row per site; all columns below) |
| `raw/<site>_window.npy` / `.tif` | The 15×15 px float32 elevation window around each point (GeoTIFF keeps georeference) |
| `raw/stac_<tile>.json` | STAC item used for each of the 6 tiles touched |
| `raw/run_log.json` | Same records as the CSV, as JSON (errors would appear here as `error`) |

## Access recipe

### Option A: STAC (Earth Search)
```python
from pystac_client import Client
cat = Client.open("https://earth-search.aws.element84.com/v1")
items = list(cat.search(collections=["cop-dem-glo-30"],
                        intersects={"type": "Point", "coordinates": [lon, lat]}).items())
href = items[0].assets["data"].href          # s3://copernicus-dem-30m/<tile>/<tile>.tif
url  = href.replace("s3://copernicus-dem-30m/", "https://copernicus-dem-30m.s3.amazonaws.com/")
```
- There is one asset, `data`. The item has `proj:transform` and `proj:shape`, so you can compute the window without opening the file. The STAC item carries no aux masks.
- Latency is **~0.75–2.0 s per search across runs** (incl. `Client.open` landing-page fetch), which is 3–5× the cost of the actual raster read.
- Tile bboxes overlap by half a pixel, so a point on an integer degree can match two items. Pick the item whose id matches the floor-rule below.

### Option B: direct bucket URL (recommended for the API)
The tile name is deterministic, so you don't need STAC:
```
Copernicus_DSM_COG_10_{N|S}{floor(lat):02d}_00_{E|W}{floor(lon):03d}_00_DEM
https://copernicus-dem-30m.s3.amazonaws.com/<tile>/<tile>.tif
```
For example, (9.95, 52.22) maps to `Copernicus_DSM_COG_10_N52_00_E009_00_DEM` (the tile covers lat 52–53, lon 9–10, named by its SW corner).
`fetch.py` asserts that the STAC href equals this computed URL for every site, and it did for all 8.
Each tile folder also holds `AUXFILES/…_{WBM,HEM,EDM,FLM}.tif` (water-body mask, height-error map, editing mask, filling mask), an ISO XML metadata file, and quicklooks.

### Window read (range requests only)
```python
import rasterio
from rasterio.windows import Window
ENV = dict(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
           CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif", GDAL_HTTP_MERGE_CONSECUTIVE_RANGES="YES")
with rasterio.Env(**ENV), rasterio.open(url) as src:          # https URL -> /vsicurl/
    T = src.transform
    col = round((lon - T.c) / T.a - 0.5); row = round((T.f - lat) / -T.e - 0.5)  # nearest pixel
    z = src.read(1, window=Window(col - 7, row - 7, 15, 15)).astype("float64")
```
`GDAL_DISABLE_READDIR_ON_OPEN=EMPTY_DIR` matters: without it, GDAL tries to list the bucket "directory".

## Raster facts (checked from the file)
- 3600 rows × 2400 cols per 1°×1° tile at 50–60°N, float32, deflate + predictor 3, **1024×1024 internal blocks**, overviews 2/4/8, `nodata=None`.
- CRS EPSG:4326. Vertical datum **EGM2008 geoid**, from the tile XML (so heights are roughly "above sea level", not ellipsoidal).
- `AREA_OR_POINT=Point`. The transform origin is offset by half a pixel (e.g. left = 8.999791667), so **pixel centres lie exactly on integer degrees** and on every 1"/1.5" step.
- Pixel spacing is Δlat = 1" (0.000277…°) and **Δlon = 1.5" (0.000416…°) between 50°N and 60°N**. All of Niedersachsen falls in this band.

## CRS / pixel size → metres
Slope needs metres in both directions. The script uses WGS84 ellipsoid radii at the point latitude φ:
```
N = a / sqrt(1 - e² sin²φ)          M = a (1 - e²) / (1 - e² sin²φ)^1.5
dx = rad(Δlon) · N · cos φ           dy = rad(Δlat) · M
```
This gives dx = 27.6 m (53.55°N) to 28.8 m (51.75°N), and dy = 30.9 m. Cells are *not square*. If you treat them as square degrees, or forget the 1.5" lon spacing, the E–W gradient is wrong by ~1.5×.

## Formulas
- **Elevation**: nearest pixel, plus bilinear on pixel-centre coordinates (`colf = (lon-left)/Δlon - 0.5`).
  *Note:* every test coordinate has 2 decimals, so it lands **exactly on a pixel centre** (0.01° = 24 px lon / 36 px lat). That makes bilinear equal nearest for all 8 sites. Arbitrary API points will differ.
- **Slope/aspect (Horn 1981)** on the 3×3 around the centre pixel, rows N→S, cols W→E, cells `a b c / d e f / g h i`:
  ```
  dz/dx = ((c+2f+i) - (a+2d+g)) / (8·dx)     # + = rising to the east
  dz/dy = ((a+2b+c) - (g+2h+i)) / (8·dy)     # + = rising to the north
  slope° = atan(√(dzdx²+dzdy²)),  slope% = 100·√(…)
  aspect = (atan2(-dzdx, -dzdy)) mod 360    # compass bearing of the DOWNSLOPE direction, 0=N, 90=E
  ```
  The script reports aspect as `flat` when slope < 0.1°, plus an 8-point compass label.
- **Smoothed slope (`slope_smooth90_*`)**: a 3×3 mean filter, then Horn with a 3-pixel step (neighbours ~85–93 m away). This damps single-pixel canopy and building steps. **Use it in the API.**
- **Relief**: max−min over the 5×5 (~150 m) and the 15×15 (~420×460 m) window.
- **TPI** = centre − mean(other 224 px of the 15×15). Positive means a local high (ridge, mound, *or roof/canopy*); negative means a hollow.
- **DSM artefact flag**: `max_step_3x3_m > 5` (a >5 m jump between the centre and a neighbour), or a raw slope >5° that is >2.5× the smoothed slope.
- **Aux masks**: the centre-pixel value of WBM (0 = no water), HEM (height error, m), and EDM (raw editing-mask code, not decoded here). HEM is -32767/nodata wherever EDM ≠ 1 (Solling, Hannover, Hamburg). The script reports those as empty.

## Per-site results (`dem_sites.csv`)

| site | elev m | slope ° (raw 3×3) | aspect raw | slope ° smooth90 | aspect smooth | relief 5×5 / 15×15 m | TPI m | max 3×3 step m | artefact? | HEM m / EDM |
|---|---|---|---|---|---|---|---|---|---|---|
| Hildesheimer Börde | 76.68 | 0.32 | N | 0.14 | N | 0.87 / 20.62 | 0.29 | 0.42 | no | 0.26 / 1 |
| Lüneburger Heide | 98.15 | 12.55 | S | 0.39 | W | 17.90 / 19.72 | 0.43 | 8.97 | **yes** | 1.18 / 1 |
| Emsland | 27.95 | 16.66 | SE | 5.35 | SE | 18.06 / 20.81 | 2.44 | 9.65 | **yes** | 0.61 / 1 |
| Wesermarsch | −0.39 | 0.24 | SW | 0.05 | flat | 0.72 / 4.45 | −0.04 | 0.56 | no | 0.52 / 1 |
| Teufelsmoor | 0.60 | 0.08 | flat | 0.04 | flat | 1.02 / 1.49 | 0.02 | 0.43 | no | 0.68 / 1 |
| Solling | 512.61 | 10.14 | S | 4.82 | SW | 26.30 / 33.24 | −0.29 | 11.92 | **yes** | – / 2 |
| Hannover centre | 56.04 | 9.79 | SW | 0.74 | SW | 12.90 / 16.15 | 0.43 | 7.42 | **yes** | – / 3 |
| Hamburg | 31.07 | 4.12 | SE | 1.10 | E | 10.65 / 15.59 | 4.78 | 5.06 | **yes** | – / 4 |

WBM = 0 (no water) at all sites. Values are as fetched on 2026-10-03; the timing numbers vary run to run.

### Reading the windows (DSM caveat in practice)
GLO-30 is a **surface** model (X-band radar), so it includes trees and buildings. Five of the 8 sites are visibly affected:
- **Emsland**: the window has a clean ~18 m plateau (ground) next to a ~35–37 m block, which is a forest stand with ~18 m canopy. The point sits on the stand edge, so the raw slope reads 16.7°. The real terrain is flat sand/peat.
- **Lüneburger Heide**: ±10 m pits and bumps from a forest/heath mosaic. The raw slope is 12.6° but the smoothed slope is 0.4°.
- **Hannover centre**: 49–65 m of building-roof noise in an area that is really flat (~52–55 m ground). The raw slope is 9.8°; smoothed it is 0.7°.
- **Solling**: real upland (~505 m plateau). On top of it are ~20–25 m blocks (spruce/beech stands versus clearings). Even the smoothed 4.8° is partly canopy-driven. Elevation can be biased high by up to roughly the canopy height.
- **Hamburg**: urban, with buildings plus the Elbe slope. TPI +4.8 m most likely reflects roofs, not a hill.
- **Clean sites**: Hildesheimer Börde (open arable loess, flat at ~76 m; one tree or building corner pixel at 96 m), Wesermarsch (−0.4 m, below sea level as expected for drained marsh), and Teufelsmoor (+0.6 m, flat bog).

Consequences: never use the raw single-pixel Horn slope. Use the smoothed slope plus the artefact flag. Treat elevation in forest and urban areas as an upper bound. For true bare-earth, use the LGLN DGM1/DGM5 for Niedersachsen (not covered here), or a DTM derived from GLO-30 (e.g. FABDEM, which has license restrictions).

## Latency & bytes (cold, vsicurl cache disabled via `CPL_VSIL_CURL_NON_CACHED`)
| step | typical |
|---|---|
| STAC search (pystac-client, incl. Client.open) | 0.75–2.0 s (1.0–1.75 s in the final run) |
| `rasterio.open` (header range request) | 130–290 ms |
| 15×15 window read | 130–265 ms |
| bytes per point | **1.0–3.4 MB** in 2 HTTP ranges (header + one compressed 1024×1024 block) |
| aux masks (WBM+HEM+EDM, 3 more opens) | 0.6–1.0 s |

Warm behaviour (separate test, same process, cache on): opening a tile once and then reading another window **in the same 1024-px block** took **~1 ms**. A different block in the same tile took ~260 ms. Byte counts come from GDAL `CPL_DEBUG` "Downloading a-b" lines, captured through rasterio's logger.

## Gotchas
1. **Block size dominates cost.** A 15×15 window still downloads one full 1024² compressed block (~1–3.4 MB; flat or water areas compress better). Window size below 1024 px doesn't change the bytes read.
2. **1.5" longitude spacing** above 50°N, so cells are non-square (28×31 m). Convert both axes to metres separately.
3. **Half-pixel origin**: pixel centres sit on integer degrees, and tiles overlap by half a pixel. Points within 7 px of a tile edge need the neighbour tile. `fetch.py` detects this and records an error instead of mosaicking. None of the test sites hit it.
4. `nodata` is not set in the GeoTIFF. Don't rely on masking; check for finite values and plausible ranges.
5. STAC hrefs are `s3://`. Rewrite them to https, or use `/vsis3/` with `AWS_NO_SIGN_REQUEST=YES`.
6. The heights are a DSM with EGM2008 heights. Negative values in marshes are real, not errors.
7. HEM is nodata on edited pixels (forest/urban sites here).
8. Some tiles in the global collection are not public (per the collection description). All of Germany was available.

## How to use this in our API
Per request point: compute the tile URL (no STAC), then do one range-read window and compute these values:

| output | derived from | soil meaning / use |
|---|---|---|
| `elevation_m` (EGM2008) | bilinear | Climate proxy (temperature lapse ~0.6 °C/100 m, precipitation increases toward Harz/Solling). Near-zero or negative values mark marsh/coastal lowland (drainage, salinity, groundwater influence). |
| `slope_deg`, `slope_pct` | **smoothed** Horn (~90 m) | Water erosion risk: the LS factor of (R)USLE/ABAG, where risk rises sharply above ~2–5 % on loess. Also tillage and machinery limits, and runoff versus infiltration. |
| `aspect_deg`, `aspect_label` | smoothed Horn (only when slope > ~2°) | Soil warming and evaporation: S/SW slopes are warmer and drier, N/NE slopes cooler and moister (earlier or later spring workability). |
| `tpi_m`, `relief_m` | 15×15 window | Topographic wetness proxy: negative TPI (hollow) plus low slope suggests accumulation (colluvium, waterlogging, gleysols). Positive TPI suggests a shedding position (eroded or thinner soils). |
| `dsm_quality_flag` | step/ratio heuristic | Downgrade confidence in forest and urban areas, and say so in the response. |

**How it complements ISRIC SoilGrids (250 m)**: SoilGrids provides modelled soil *properties* (texture, SOC, pH, bulk density) at 250 m and already uses DEM covariates internally. GLO-30 adds **30 m terrain context** that SoilGrids smooths out. That covers within-field slope and erosion position, hollows versus crests for wetness, and exposure. Together they let the API combine "what the soil is" (SoilGrids/BÜK200) with "how the landscape treats it" (DEM), e.g. erodibility from SoilGrids silt/sand/SOC (K-factor) × slope from GLO-30 to get an erosion-risk class. For flat lowlands (marsh, bog), the DEM's main value is absolute elevation relative to sea level and drainage. Slope and aspect there are ~0 and should be reported as flat.

Implementation tips: keep one opened `rasterio` dataset per tile in a process-wide LRU and leave the GDAL vsicurl cache on (do not set `CPL_VSIL_CURL_NON_CACHED` in production). Optionally cache decoded 1024² blocks (4 MB float32 each). Skip STAC on the hot path.
