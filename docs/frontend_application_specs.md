| Data Source | Format | Description |
| :--- | :--- | :--- |
| Copernicus DEM | GeoTIFF (COG) | Float32 raster, EPSG:4326, elevations in meters |
| LGLN DGM1 | GeoTIFF via WCS | 1m raster, EPSG:25832 |
| Open-Meteo | JSON | Hourly and daily time series, no geometry |
| SMAP L4 | CSV (AppEEARS) | 3-hour series per point |
| BÜK200 | GeoJSON / ArcGIS JSON | Vector polygons with German text attributes |
| SoilGrids | JSON (REST) or GeoTIFF | Quantile values in mapped units (g/kg, pH $\times 10$) |
| LBEG | Text or XML (GetFeatureInfo) | Point attributes, no geometry |
| Parcels | GeoJSON | Field polygons |

## v1.0 Frontend Application Features

1. Property map with confidence (as requested in the brief)
* Texture, pH, organic carbon, nFK, and Bodenzahl, from 0 to 30 cm.
* Each featuring its central value, range, and a confidence color.
* Red or "unknown" zones are striped in grey, never painted as if they were a definitive value.

2. Source discrepancy map
* Answers the question: "Multiple sources say different things about the same field," which is literally the core challenge.
* Serves as the key demo image: the before (separate sources) versus the after (fusion with confidence).

3. Sampling plan
* Answers: "If you are going to pay for 5 analyses, take them here."
* Prioritizes points where uncertainty changes a decision (e.g., pH near the lime threshold), rather than where uncertainty is highest.
* Exportable as GPS points.
* Closes the loop: with these samples, the next execution can be calibrated (Level B).

4. Management signals
* Lime, drought, erosion, compaction, and nitrate.
* Expressed with certainty words (probable, possible, unlikely, no, unknown) and without application rates.
* For the agronomist, this translates most rapidly into a decision.

5. Parcel datasheet with two views
* Farmer view: simple phrasing.
* Audit view: ranges, sources with citation and license, and rationale.
* Covers 15% of the auditability score.

## Frontend Application Enhancements (Out of Scope)

1. Crop suitability with limiting factor (recommended)
* For each parcel or zone, a class for typical regional crops (wheat, barley, rye, rapeseed, corn, sugar beet, potato, grassland): well-adapted, limited, or poorly adapted.
* The real value lies in the "why": "Sugar beet: limited. Limiting factor: low available water capacity." "Rye: well-adapted."
* Fits with what is already built: rule-based thresholds, Monte Carlo, and certainty wording—never crop yield figures.
* Risk: crop thresholds (pH, texture, nFK, waterlogging) are not yet verified.

2. Dynamic layers: static soil with current moisture (recommended)
* Tillage window (workability): texture + TWI + Open-Meteo moisture percentile. Example: "This week: high zone passable; depression, compaction risk." This is the compaction rule, but with a date.
* Seasonal water stress: nFK + 30-day water balance. Example: "Sandy zones are drier than 85% of years on this date."
* Sowing window: soil temperature vs. crop-specific threshold (thresholds to be verified).
* This gives meaning to the 14-day update cycle and shines in the demo with incremental refreshes.