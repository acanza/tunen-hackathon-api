import type { Meta } from '../api/types'

// Plain-language versions of the key rows of the `validation` table (poc/VALIDATION.md).
type V = Meta['validation'][number]

export interface ValidationLine {
  key: string
  topic: 'yield' | 'bodenzahl' | 'texture' | 'soil_model'
  text: string
  audit: string
}

const pct = (v: number | null) => (v == null ? '–' : `${Math.round(v * 100)} %`)
const num = (v: number | null, d = 2) => (v == null ? '–' : v.toFixed(d))

const RULES: Array<{ metric: string; scope: string; topic: ValidationLine['topic']; text: (v: V) => string; audit: (v: V) => string }> = [
  {
    metric: 'loyo_agree_v1_median', scope: 'all_seasons', topic: 'yield',
    text: (v) => `Tested on seasons the model never saw: ${pct(v.value)} of the field lands on the correct side of its average.`,
    audit: (v) => `Leave-one-season-out, median above/below-mean agreement ${num(v.value)} (n = ${v.n} field-seasons).`,
  },
  {
    metric: 'loyo_rho_v1_median', scope: 'all_seasons', topic: 'yield',
    text: (v) => `The pattern holds up moderately from year to year (rank correlation ${num(v.value)}).`,
    audit: (v) => `Leave-one-season-out, median per-field Spearman ρ ${num(v.value)} (n = ${v.n}).`,
  },
  {
    metric: 'loyo_share_v1_beats_flat_rmse', scope: 'all_seasons', topic: 'yield',
    text: (v) => `The map beats “every part of the field is average” in ${pct(v.value)} of tested field-seasons.`,
    audit: (v) => `Share of field-seasons where v1 RMSE < flat RMSE: ${num(v.value)} (n = ${v.n}).`,
  },
  {
    metric: 'bodenzahl_derived_rmse_grouped_by_parcel', scope: 'gradient_boosting', topic: 'bodenzahl',
    text: (v) => `Our Bodenzahl model is typically within about ${Math.round(v.value ?? 0)} points of the official survey.`,
    audit: (v) => `Gradient boosting, RMSE per parcel ${num(v.value, 1)} points, grouped CV on ${v.n} Bodenschätzung parcels.`,
  },
  {
    metric: 'texture_soilgrids_share_in_class_range', scope: 'west_parcels', topic: 'texture',
    text: (v) => `SoilGrids clay matches the official soil class on only ${pct(v.value)} of surveyed parcels.`,
    audit: (v) => `Share of parcels whose SoilGrids clay % lies in the Bodenart's clay range: ${num(v.value)} (n = ${v.n}).`,
  },
  {
    metric: 'soil_model_r2_grouped_cv', scope: 'all_fields', topic: 'soil_model',
    text: () => 'Soil and terrain alone don’t predict the yield pattern; it comes from satellite history.',
    audit: (v) => `Soil/terrain prior, grouped-CV R² ${num(v.value, 3)} (${v.n} px).`,
  },
]

export function validationLines(meta: Meta | undefined, topic?: ValidationLine['topic']): ValidationLine[] {
  if (!meta) return []
  return RULES.filter((r) => !topic || r.topic === topic).flatMap((r) => {
    const v = meta.validation.find((x) => x.metric === r.metric && x.scope === r.scope)
    return v ? [{ key: `${r.metric}:${r.scope}`, topic: r.topic, text: r.text(v), audit: r.audit(v) }] : []
  })
}
