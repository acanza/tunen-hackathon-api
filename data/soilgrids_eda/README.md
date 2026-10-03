# ISRIC SoilGrids v2.0: exploratory data analysis

Global soil property predictions at 250 m resolution, with an uncertainty estimate.
This folder holds a point-query pull for 7 test sites in and around Niedersachsen.

## Files

| File | What it is |
|---|---|
| `fetch.py` | Pulls 14 properties × 7 depths × 5 statistics for each site from the REST API and flattens the JSON into the CSV. Run: `uv run fetch.py` (≈15 min). |
| `summarize.py` | Prints the tables used in this README. Run: `uv run summarize.py`. |
| `soilgrids_sites.csv` | 2,765 rows, long format (see below). |
| `units.json` | `unit_measure` block per property, copied from the API responses. |

The raw JSON responses were **not** saved; they were parsed in memory and flattened.
The `raw` column holds the API integers exactly as returned (written as floats, e.g. `192.0`, because the column contains nulls).
A spot check that re-queried the API live matched 20/20 values.

### CSV columns

| Column | Meaning |
|---|---|
| `site` | Our label for the location (not from SoilGrids) |
| `lon`, `lat` | WGS84 coordinates queried |
| `prop` | SoilGrids property code (table below) |
| `depth` | `0-5cm`, `5-15cm`, `15-30cm`, `30-60cm`, `60-100cm`, `100-200cm` (only `ocs` uses `0-30cm`) |
| `stat` | `Q0.05`, `Q0.5`, `Q0.95`, `mean`, `uncertainty` |
| `raw` | Integer value as returned by the API (empty = null) |
| `value` | `raw / d_factor` (for `uncertainty`: `raw / 10`) |
| `unit` | Unit of `value` |

## API

```
GET https://rest.isric.org/soilgrids/v2.0/properties/query
    ?lon=9.95&lat=52.22
    &property=clay&property=phh2o            # repeatable
    &depth=0-5cm&depth=30-60cm               # repeatable
    &value=Q0.5&value=Q0.05&value=Q0.95      # repeatable
```

- No API key. Fair-use limit ≈ 5 requests/min.
- **Slow:** 30–45 s per request no matter how many properties are asked for (one took 97 s). All 14 properties in one call timed out after 120 s; chunks of 5 properties worked.
- `query_time_s` in the response is server-side time only (≈0.3 s), not what you wait for.
- `GET /properties/layers` lists properties, depths and statistics.

### Response structure

GeoJSON `Feature`. Coordinates are `[lon, lat]`, longitude first.

```
properties.layers[]            one per property
  .name                        "clay"
  .unit_measure.d_factor       divide raw by this
  .unit_measure.mapped_units   unit of the raw integer
  .unit_measure.target_units   unit after dividing
  .depths[]
    .label                     "0-5cm"
    .range.top_depth / bottom_depth (cm)
    .values                    {"Q0.5": 192, "mean": 295, ...} or null
```

## Properties and units

| Code | Property | Raw unit | ÷ | Display unit |
|---|---|---|---|---|
| `bdod` | Bulk density | cg/cm³ | 100 | g/cm³ |
| `cec` | Cation exchange capacity (pH 7) | mmol(c)/kg | 10 | cmol(c)/kg |
| `cfvo` | Coarse fragments (>2 mm) | cm³/dm³ | 10 | vol % |
| `clay` / `sand` / `silt` | Texture fractions | g/kg | 10 | % (sum to 100) |
| `nitrogen` | Total nitrogen | cg/kg | 100 | g/kg |
| `ocd` | Organic carbon density | dg/dm³ | 10 | kg/m³ |
| `ocs` | Organic carbon stock, **0–30 cm only** | t/ha | 10 | kg/m² (×10 = t/ha) |
| `phh2o` | pH in water | pH×10 | 10 | pH |
| `soc` | Soil organic carbon | dg/kg | 10 | g/kg |
| `wv0010` | Water content at 10 kPa | 0.1 vol % | 10 | vol % |
| `wv0033` | Water content at 33 kPa (≈ field capacity) | 0.1 vol % | 10 | vol % |
| `wv1500` | Water content at 1500 kPa (≈ wilting point) | 0.1 vol % | 10 | vol % |

Plant-available water ≈ `wv0033 − wv1500`.

## How the numbers are produced

Source: Poggio et al. 2021, *SOIL* 7:217–240, <https://soil.copernicus.org/articles/7/217/2021/>

- **Model:** quantile regression forest (QRF; `ranger` with `quantreg`), one model per property.
- **Training data:** ≈240,000 profiles (≈920,000 layers) from ISRIC WoSIS.
- **Covariates:** 400+ environmental layers (climate, terrain, remote sensing, land cover, geology), reduced to ≈150 by removing correlated layers, then to **15–20 per property** by recursive feature elimination.
- **Depth** is a covariate (midpoint of the sampled layer). The 6 depths are 6 predictions from the same model, with **no constraint that neighbouring depths agree**.
- **Texture** was modelled after an additive log-ratio transformation, so clay + sand + silt = 100 %.
- **No residual kriging:** values come only from the covariates.

### Quantiles, mean and uncertainty

A QRF keeps every training observation in each leaf. For a new location, training samples get weighted by how often they share a leaf with it across the trees. That weighted set is a predicted distribution:

- `Q0.05`, `Q0.5`, `Q0.95` = quantiles of that distribution (90 % prediction interval).
- `mean` = ordinary random-forest mean.
- `uncertainty` = `(Q0.95 − Q0.05) / Q0.5 × 10`, rounded.
  Verified on our data: 395 combinations, 99.5 % within ±1 of the recomputed value, max gap 1.46 (rounding).
- Validation: in cross-validation, 88–92 % of held-out observations fell inside the 90 % interval. That is calibration **on average worldwide**, not necessarily in Niedersachsen.

How to read `uncertainty / 10`:

| Value | Meaning |
|---|---|
| < 1 | 90 % range narrower than the median, fairly confident (pH: 0.4–0.7) |
| 1–3 | Wide |
| > 3 | Range is several times the median, close to uninformative (clay 2.5–6, topsoil SOC 6–10) |

It blows up when the median is small (e.g. subsoil SOC at Wesermarsch 30–60 cm: 40). Show the absolute Q0.05–Q0.95 range alongside it.

## Test sites

| Site | lon, lat | Result |
|---|---|---|
| Hildesheimer Börde (loess) | 9.95, 52.12 | **All null.** Not urban: LBEG BK50 maps this point as arable land (Pseudogley-Parabraunerde). `9.95, 52.22` has data (clay 11.8 %, SOC 19.9 g/kg). |
| Lüneburger Heide (sand) | 10.05, 53.05 | Data |
| Emsland (sand/peat) | 7.35, 52.75 | Data |
| Wesermarsch (marsh clay) | 8.40, 53.35 | Data |
| Teufelsmoor (bog) | 8.90, 53.25 | Data |
| Solling (upland forest) | 9.55, 51.75 | Data |
| Hannover centre (urban) | 9.73, 52.37 | **All null** |

Also checked:
- `10.10, 52.18` (open farmland): all null.
- `9.95, 53.55` (Hamburg centre, `data/9.950_53.550/soilgrids.json`): all null.

Site labels are our guesses about the landscape, not SoilGrids output. The sites were picked by hand and are not a representative sample.

### Topsoil 0–5 cm, mean

| Site | clay % | sand % | pH | SOC g/kg | bdod g/cm³ | wv0033 → wv1500 vol % |
|---|---|---|---|---|---|---|
| Emsland | 5.5 | 82 | 4.9 | 109 | 0.98 | 37 → 7 |
| Lüneburger Heide | 8.3 | 71 | 4.9 | 86 | 0.97 | 39 → 10 |
| Solling | 26.4 | 22 | 4.4 | 135 | 0.90 | 39 → 19 |
| Teufelsmoor | 36.3 | 23 | 5.4 | 143 | 1.07 | 38 → 16 |
| Wesermarsch | 29.5 | 21 | 5.5 | 123 | 1.09 | 38 → 19 |

### Median vs mean, topsoil SOC (g/kg)

| Site | Q0.05 | Q0.5 | mean | Q0.95 |
|---|---|---|---|---|
| Emsland | 10.3 | 44.4 | 109.2 | 450.3 |
| Lüneburger Heide | 8.5 | 36.7 | 85.6 | 392.7 |
| Solling | 7.2 | 68.2 | 134.5 | 435.5 |
| Teufelsmoor | 10.5 | 76.0 | 142.6 | 450.3 |
| Wesermarsch | 15.0 | 61.0 | 122.7 | 435.0 |

## Findings

1. **Nulls are all-or-nothing per pixel.** A point either has every property at every depth, or none. Nulls appear in cities (Hannover, Hamburg) and **also on farmland** (`9.95, 52.12` and `10.10, 52.18`, both arable land per BK50). Any API built on this needs a fallback (BK50 in Niedersachsen, BÜK200 elsewhere).
2. **Use the median (`Q0.5`) for display, not `mean`.** SOC and clay are right-skewed; the mean is pulled up by peaty training samples (Emsland SOC: median 44, mean 109 g/kg).
3. **Intervals are wide.** Clay at Wesermarsch: 0.5–83 %. SOC everywhere: ≈10–450 g/kg. Only pH is fairly tight (±≈1.5).
4. **Profiles can zigzag** because depths are separate predictions (Emsland SOC: 109 → 37 → 47 g/kg). Don't present them as one measured profile.
5. **Peat is poorly represented.** Teufelsmoor (bog) comes out as 36 % mineral clay.
6. **Broad patterns are right:** sandy sites (Emsland, Heide) vs clay-rich sites (marsh, bog, upland); pH and bulk density rise with depth.
7. **`ocs` (0–30 cm carbon stock)** must be requested with `depth=0-30cm`; other depths don't exist for it.

## How to use it in our API

- Global baseline when nothing better exists, and the natural source for a **confidence layer** (it is the only source here with a per-value uncertainty).
- Show `Q0.5` with the `Q0.05–Q0.95` range; map `uncertainty` to a confidence label.
- Batch properties, depths and statistics into a few requests per point and **cache by coordinate**. Never call it live in a user request path.
- Treat "all null" as "no data here" and fall back to another source.
- Inside Niedersachsen, prefer LBEG BK50 for texture and available water.
