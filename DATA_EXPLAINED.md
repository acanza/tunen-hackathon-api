# Data Explanation

## SoilGrids v2.0 (ISRIC)
The `soilgrids.json` file contains responses from ISRIC's REST API. Each key follows the pattern `property_depth_value` (or as queried).

### Structure
```json
{
  "clay_0-5cm_mean": {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [lon, lat]},
    "properties": {
      "layers": [{
        "name": "clay",
        "unit_measure": {
          "d_factor": 10,
          "mapped_units": "g/kg",
          "target_units": "%",
          "uncertainty_unit": ""
        },
        "depths": [{
          "range": {"top_depth": 0, "bottom_depth": 5, "unit_depth": "cm"},
          "label": "0-5cm",
          "values": {"mean": ...}
        }]
      }]
    }
  }
}
```

### Important Notes
- **Units**: The `mapped_units` and `d_factor` matter. For example, clay is in `g/kg` with `d_factor: 10` in some cases; values may need conversion as noted in dataset.md (e.g., pH ×10). Check the API docs for specifics.
- **Missing data**: Some coordinates return `null` values (as seen for (9.95°, 53.55°) in parts of northern Germany). This is expected - SoilGrids has global coverage but values can be null depending on location/model uncertainty.
- **Quantiles**: Without specifying `value`, the API returns all statistics: `Q0.05`, `Q0.5` (median), `Q0.95`, `mean`, and `uncertainty` where available.
- **Depths**: Standard depths are 0-5, 5-15, 15-30, 30-60, 60-100, 100-200 cm.

## Open-Meteo
The `openmeteo.json` contains historical hourly data from ERA5-Land.

### Structure
- `latitude`, `longitude`, `elevation`, `timezone`
- `hourly_units`: units for each variable (e.g., `soil_moisture_0_to_7cm` in `m³/m³`, time in `iso8601`)
- `hourly`: arrays for `time` and requested variables (hourly timestamps aligned with values)

### Variables (sample)
- `soil_moisture_0_to_7cm`: Volumetric soil water content in m³/m³
- Other depth bands available: 7-28 cm, 28-100 cm, 100-255 cm
- Also includes `soil_temperature_*`, `precipitation`, `et0_fao_evapotranspiration` if requested

## Other APIs (from dataset.md)
- **LBEG BK50/NIBIS (WMS)**: Returns map features via GetCapabilities/GetFeatureInfo; German soil classification, plant-available water, yield capability. Requires WMS point queries.
- **BGR BÜK200 (ArcGIS REST)**: Federal soil overview (1:200k); use identify/query operations. Returns soil type/parent material.
- **Copernicus DEM GLO-30 (STAC)**: 30m elevation; read as raster (COGs) using rasterio/rioxarray for point extraction.
