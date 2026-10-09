// Why a layer is missing or partial (poc/UI_BRIEF.md "Reasons for missing layers", poc/API_BRIEF.md closed lists).
export const REASONS: Record<string, string> = {
  'outside_source_region:niedersachsen': 'The state soil survey only covers Lower Saxony; this field is in Saxony-Anhalt.',
  attribute_not_in_downloaded_data: 'This value exists in the state map but isn’t in our data yet.',
  no_parcel_downloaded_for_field: 'The survey covers this field, but we haven’t loaded it yet.',
  outside_coverage_area: 'Outside the area we have data for.',
  no_data_in_source: 'The source has no value here.',
  not_precomputed_for_this_polygon: 'This shape isn’t one of the farm’s known fields; we can’t compute it yet.',
  source_does_not_provide_parameter: 'This source doesn’t provide this value.',
  only_parcels_at_sample_point_downloaded: 'Only the survey parcels at the field’s sample point are loaded.',
  partial_source_coverage: 'The source covers only part of the field.',
}

export const reasonText = (reason: string | null | undefined) => (reason ? (REASONS[reason] ?? reason) : '')
