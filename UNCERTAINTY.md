# Measuring confidence in soil layers

How to measure the uncertainty of each soil property, source and pixel, and show it to farmers in a way they can act on.

Applies to texture, pH, SOC, nFK, Bodenzahl and the derived yield potential layer.

## The principle

**Confidence is an uncertainty range around the value, not a separate score you make up.** Work out a plausible range for each pixel, then turn that range into something a farmer can read.

A range has a physical meaning ("pH is probably between 5.4 and 6.2"), it can be compared across sources, and it can be checked against data. An abstract score such as "0.73 confidence" has none of these properties.

## Where uncertainty comes from

Eight drivers determine how far a displayed value can be trusted. Some give a range directly. Others can only lower the confidence level.

| # | Driver | How to measure it | Example on Seggerde |
|---|---|---|---|
| 1 | **Source's own uncertainty** | SoilGrids publishes quantiles for each property (`Q0.05`, `Q0.5`, `Q0.95`). Use the 90 % range directly. | SoilGrids pH 5.8, 90 % range 5.1–6.6 |
| 2 | **Map scale vs. field size** | Use the scale as a prior: Bodenschätzung 1:5k > BK50 1:50k > BÜK200 1:200k > SoilGrids 250 m. Also count how many independent source cells actually cover the field. | A 3 ha field inside one SoilGrids cell is effectively one sample |
| 3 | **Agreement between sources** | Where sources overlap, convert them to the same units and take the spread: `σ_between = std(values)`. | West: SoilGrids clay vs. BK50 clay |
| 4 | **Calibrated error** | Treat the detailed western data as ground truth. Measure SoilGrids and BÜK200 error against Bodenschätzung there (RMSE, bias), then apply that error to eastern fields that only have coarse sources. | "In this region SoilGrids clay is usually ±8 % off" |
| 5 | **Coverage and data quality** | Share of the field the source covers. For NDVI: clean observations per pixel and cloud gaps. For weather: distance to the grid cell centre (ERA5 ≈ 31 km, ERA5-Land ≈ 9 km). | NIBIS covers 21 % of `Silbersee` |
| 6 | **Stability over time** | For NDVI and yield potential: coefficient of variation across seasons. A zone that swings between weak and strong is a low-confidence zone. | Relative NDVI 2019–2025 per pixel |
| 7 | **Field edges** | Pixels that mix crop with hedges or roads, plus the headland strip. Mark them low, or leave them out of statistics with an inner buffer of about 10–20 m. | Outer 1–2 Sentinel-2 pixels of each field |
| 8 | **Model error (derived layers)** | nFK from a pedotransfer function: published PTF error plus input uncertainty. Yield potential: residuals of the soil model and disagreement between the NDVI and soil estimates. | nFK estimated from texture + SOC in the east |

## Combining the drivers

Where a driver can be expressed as a standard deviation, add the variances to get one range for each pixel:

```
σ_total² = σ_source² + σ_between² + σ_calibration²   (+ σ_model² for derived layers)

range_90 = value ± 1.64 · σ_total
```

Some drivers can't be expressed as a σ: partial coverage, edge pixels, outdated surveys. These don't widen the range. They **lower the confidence level** by one step, or set it to low.

### Converting sources to a σ

- **SoilGrids:** `σ ≈ (Q0.95 − Q0.05) / 3.29`, assuming the 90 % range is roughly symmetric.
- **Vector maps without stated error** (BK50, BÜK200): use the calibrated RMSE from driver 4, or a default per map scale until you have one.
- **Bodenschätzung:** treat it as the reference (lowest σ). It is reliable at field scale, but each field currently has only one point value. Query several points per field to capture variation within it.

## Tying it to decisions

The farmer doesn't care about σ. They care whether it changes what they do, so **compare the range with the agronomic threshold that drives the decision**.

Example with a liming threshold of pH 5.5 (the actual target depends on soil texture class):

```
            5.0       5.5       6.0       6.5       7.0
             |---------|---------|---------|---------|
                       ┆
pH 5.8                ●━━━━━━━━━━━━━━━━━●            crosses threshold → LOW
pH 6.5                 ┆        ●━━━━━━━━━━━━━━━━━━●  wide, one side   → MEDIUM
pH 6.8                 ┆                   ●━━━━━●    narrow, clear    → HIGH
                       ┆
                 liming threshold
```

| Level | Rule | Message to the farmer |
|---|---|---|
| 🟢 **High** | The range doesn't cross a decision threshold, sources agree, and the source is detailed. | "Confident: no liming needed" |
| 🟡 **Medium** | The range is wide but stays on one side of the threshold, *or* only one coarse source covers the pixel. | "Likely fine, based on coarse data" |
| 🔴 **Low** | The range crosses a threshold, sources disagree, coverage is low, or the pixel is on an edge. | "Uncertain: soil sample recommended" |

Properties without a clear threshold (SOC, texture) can use the width of the range relative to the parameter's agronomic range instead. For example, a 90 % range wider than one texture class means medium at best.

## UI and API

### On the map

- Hatch or fade low-confidence areas. Don't hide them; the farmer still needs to see the value.
- Show the range and the reason on hover:

  > **pH 5.8** · likely 5.4–6.2 · 🟡 Medium
  > Based on SoilGrids 250 m. No detailed state map covers this field.

### In the API response

Add a `confidence` block to each layer, next to `stats` and `colormap`:

```json
"confidence": {
  "level": "medium",
  "interval_90": [5.4, 6.2],
  "drivers": ["single_coarse_source", "no_state_map_coverage"],
  "raster_url": "/rasters/f1/ph/soilgrids_conf.tif"
}
```

- `level`: field-level summary, for badges and lists.
- `interval_90`: the range behind the level, for tooltips and legends.
- `drivers`: machine-readable reasons. These build trust because they tell the farmer *why* confidence is low and *what would raise it*, usually a soil sample in that zone.
- `raster_url`: per-pixel confidence on the same grid as the value raster, so the UI can hatch only the uncertain parts of a field.

## Where to start

1. **Calibrate on the western fields.** About 240 ha in Niedersachsen have BK50 and Bodenschätzung from NIBIS (`data/seggerde/nibis/`). Compare SoilGrids and BÜK200 against them to get a measured error (driver 4).
2. **Pull the SoilGrids quantiles** alongside the mean, so driver 1 is available everywhere.
3. **Apply the calibrated error to the east** (about 645 ha in Sachsen-Anhalt), where only coarse sources exist.
4. **Add the threshold rules** for pH and nFK first, since they map most directly to farmer decisions (liming, irrigation).

The calibration step is the most valuable one. It replaces an assumed error with a measured error from the same landscape, and the data for it is already in `data/seggerde/`.
