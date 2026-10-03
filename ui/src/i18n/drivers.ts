// Confidence driver codes → farmer / audit text (poc/UI_BRIEF.md, "Driver codes").
export const DRIVERS: Record<string, { farmer: string; audit: string }> = {
  single_coarse_source: { farmer: 'Based on a coarse global map only.', audit: 'Single source, SoilGrids 250 m.' },
  pixel_larger_than_field: { farmer: 'The map is coarser than this field.', audit: 'Field smaller than one 250 m SoilGrids cell (6.25 ha).' },
  'range_crosses_threshold:liming_ph_5.5': { farmer: 'Can’t tell whether liming is needed.', audit: '90 % range crosses pH 5.5.' },
  'range_crosses_threshold:nfk_90_140_mm': { farmer: 'Can’t tell how much water the soil holds.', audit: '90 % range crosses 90 or 140 mm.' },
  'range_crosses_threshold:bodenzahl_30_50': { farmer: 'Soil quality class uncertain.', audit: '90 % range crosses Bodenzahl 30 or 50.' },
  range_wider_than_texture_class: { farmer: 'Soil type uncertain.', audit: '90 % range wider than one texture class.' },
  range_wider_than_half_value: { farmer: 'Organic matter estimate rough.', audit: '90 % range wider than half the value.' },
  error_calibrated_west: { farmer: 'Checked against the state survey nearby.', audit: 'Interval from RMSE vs Bodenschätzung, 37 parcels (VALIDATION §5).' },
  official_survey_1to5000: { farmer: 'From the official soil survey.', audit: 'Bodenschätzung, LBEG, 1:5 000.' },
  official_survey_lagb_1to10000: { farmer: 'From the official soil survey (Saxony-Anhalt).', audit: 'Bodenschätzung Klassenzeichen, LAGB Sachsen-Anhalt open data, 1:10 000.' },
  bodenzahl_from_class_lookup_west: {
    farmer: 'Saxony-Anhalt publishes the soil class, not the score: estimated from matching classes in Lower Saxony.',
    audit: 'No Bodenzahl published in ST; mean of western parcels with the same Klassenzeichen, interval = their range ±5.',
  },
  interval_assumed_not_calibrated: { farmer: '', audit: 'Interval ±5 points assumed.' },
  partial_coverage: { farmer: 'Only part of the field is covered.', audit: 'Source covers < 95 % of the field.' },
  no_inner_zone_edge_pixels_only: { farmer: 'Field too narrow for reliable values.', audit: 'No pixels ≥ 20 m from the edge; full field used.' },
  buek200_1to200000_nearest_point: { farmer: 'From the federal soil overview map.', audit: 'BÜK200 1:200 000 unit at the nearest sample point.' },
  lookup_table_approximate: { farmer: 'Estimated from soil-profile tables.', audit: 'KA5 lookup values approximate (±30 mm at 90 %).' },
  model_trained_on_38_parcels: { farmer: 'Estimated by our model.', audit: 'Trained on 38 Bodenschätzung parcels; CV RMSE 6.9 points.' },
  extrapolated_across_state_border: { farmer: 'Estimated from neighbouring Lower Saxony.', audit: 'Model applied outside its training region (Sachsen-Anhalt).' },
  reconciled_best_source_per_pixel: { farmer: 'Best available source used for each spot.', audit: 'Per-pixel ranking; see source mask.' },
  mixed_sources_in_field: { farmer: 'Parts of the field come from different sources.', audit: '> 1 source in the stats zone; see source shares.' },
  no_official_survey_model_only: { farmer: 'No official survey here: estimated by our model.', audit: 'Bodenzahl from the model only.' },
  ndvi_proxy_not_yield: { farmer: 'Based on crop growth seen from satellites.', audit: 'Relative peak NDVI (Sentinel-2), not yield.' },
  no_harvest_data_for_validation: { farmer: 'Not checked against harvests.', audit: 'No yield-monitor or harvest data.' },
  edge_strip_soil_model_weighted: { farmer: 'The field edge is less certain.', audit: 'Outer 10 m from the soil/terrain prior.' },
  soil_model_only: { farmer: 'No satellite history for this field: pattern unknown.', audit: 'No usable NDVI; soil/terrain prior only (R² ≈ 0).' },
  no_ndvi_history: { farmer: 'No satellite history for this field: pattern unknown.', audit: 'No usable NDVI; soil/terrain prior only (R² ≈ 0).' },
  few_ndvi_seasons: { farmer: 'Few years of satellite data.', audit: 'Median < 6 usable seasons.' },
  unstable_or_edge_pixels: { farmer: 'The pattern changes between years in parts of the field.', audit: '> 25 % of pixels low (unstable zone or edge).' },
}

/** Farmer text, deduplicated; drivers with no farmer text are skipped. Unknown codes fall back to the code. */
export function farmerDrivers(codes: string[]): string[] {
  return [...new Set(codes.map((c) => (c in DRIVERS ? DRIVERS[c].farmer : c)).filter(Boolean))]
}

export const auditDriver = (code: string) => DRIVERS[code]?.audit ?? code
