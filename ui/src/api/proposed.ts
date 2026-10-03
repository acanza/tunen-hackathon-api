import { z } from 'zod'

// Shapes PROPOSED in poc/UI_BRIEF.md for data the store doesn't produce yet (🔴 features). Field names are a
// proposal to agree with the API developer; the UI renders them from mock fixtures with a "preview" badge.

export const SamplingPoint = z.looseObject({
  rank: z.number(),
  lat: z.number(),
  lon: z.number(),
  decision: z.string(),
  parameter: z.string(),
  decision_uncertainty: z.number(),
  current_estimate: z.number(),
  interval_90: z.tuple([z.number(), z.number()]),
  why: z.string(),
})
export const SamplingPlan = z.looseObject({
  points: z.array(SamplingPoint),
  rules: z.looseObject({ min_spacing_m: z.number(), edge_buffer_m: z.number(), max_points: z.number() }),
  covers_ha: z.number(),
})

export const Keyword = z.enum(['Probable', 'Possible', 'Unlikely', 'No', 'Unknown'])
export const Signal = z.looseObject({
  signal: z.enum(['liming', 'drought_risk', 'erosion', 'compaction', 'nitrate_leaching']),
  keyword: Keyword,
  probability: z.number().nullable(),
  because: z.array(z.string()),
  farmer_text: z.string(),
  audit: z.looseObject({ inputs: z.record(z.string(), z.unknown()), rule: z.string() }),
})

export const Rating = z.enum(['Well adapted', 'With limitations', 'Poorly adapted'])
export const CropSuitability = z.looseObject({
  crop: z.string(),
  rating: Rating,
  limiting_factors: z.array(z.string()),
  text: z.string(),
  confidence: z.enum(['low', 'medium', 'high']),
  inputs: z.record(z.string(), z.unknown()).optional(),
})

export const Discrepancy = z.looseObject({
  parameter: z.string(),
  source: z.literal('discrepancy'),
  status: z.string(),
  png_url: z.string().nullable(),
  stats: z.looseObject({ share_conflict: z.number(), pairs: z.array(z.string()) }),
  explanation: z.string(),
})

export const FieldSummary = z.looseObject({
  productivity_rank_pct: z.number(),
  seasons: z.number(),
  note: z.string(),
})

export const Proposed = z.looseObject({
  plot_id: z.string(),
  sampling_plan: SamplingPlan.optional(),
  signals: z.array(Signal).optional(),
  crop_suitability: z.array(CropSuitability).optional(),
  discrepancy: z.array(Discrepancy).optional(),
  field_summary: FieldSummary.optional(),
})

export type SamplingPoint = z.infer<typeof SamplingPoint>
export type SamplingPlan = z.infer<typeof SamplingPlan>
export type Keyword = z.infer<typeof Keyword>
export type Signal = z.infer<typeof Signal>
export type Rating = z.infer<typeof Rating>
export type CropSuitability = z.infer<typeof CropSuitability>
export type Discrepancy = z.infer<typeof Discrepancy>
export type FieldSummary = z.infer<typeof FieldSummary>
export type Proposed = z.infer<typeof Proposed>
