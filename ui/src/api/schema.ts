import { z } from 'zod'

// The API contract (poc/API_BRIEF.md, poc/samples/response.json) as zod schemas. Types are inferred from
// these, and tests parse the sample response and all mock fixtures with them, so contract drift fails tests.
// Objects are loose: unknown keys (e.g. a future `masked_png_url`) pass through.

export const PARAMETERS = ['texture', 'ph', 'soc', 'nfk', 'bodenzahl', 'yield_potential'] as const
export const SOURCES = ['soilgrids', 'lbeg_bk50', 'lbeg_bodenschaetzung', 'derived', 'best'] as const

export const Parameter = z.enum(PARAMETERS)
export const Source = z.enum(SOURCES)
export const Status = z.enum(['ok', 'partial', 'unavailable', 'not_applicable'])
export const Level = z.enum(['low', 'medium', 'high'])
export const Match = z.enum(['plot_id', 'plot_id_geometry_differs', 'geometry', 'clipped', 'outside_coverage_area'])
export const Zone = z.enum(['inner_20m', 'inner_10m', 'full_field_fallback', 'full_field_all_touched'])

const Stop = z.tuple([z.number(), z.string()])
export const CategoricalClass = z.looseObject({
  value: z.number(),
  code: z.string(),
  label: z.string().optional(),
  color: z.string(),
})
export const Colormap = z.discriminatedUnion('type', [
  z.looseObject({ type: z.literal('continuous'), unit: z.string().optional(), stops: z.array(Stop) }),
  z.looseObject({ type: z.literal('diverging'), unit: z.string().optional(), center: z.number(), stops: z.array(Stop) }),
  z.looseObject({ type: z.literal('categorical'), unit: z.string().optional(), classes: z.array(CategoricalClass) }),
])

export const Stats = z.looseObject({
  zone: Zone,
  n_px: z.number(),
  // continuous
  mean: z.number().optional(),
  std: z.number().optional(),
  min: z.number().optional(),
  p10: z.number().optional(),
  p50: z.number().optional(),
  p90: z.number().optional(),
  max: z.number().optional(),
  // texture / soilgrids extras
  clay_mean: z.number().optional(),
  sand_mean: z.number().optional(),
  silt_mean: z.number().optional(),
  usda_class: z.string().optional(),
  // categorical
  classes: z.record(z.string(), z.number()).optional(),
  dominant: z.string().optional(),
  klassenzeichen: z.array(z.string()).optional(),
  // best
  source_shares: z.record(z.string(), z.number()).optional(),
})

export const Confidence = z.looseObject({
  level: Level,
  interval_90: z.tuple([z.number(), z.number()]).nullable(),
  drivers: z.array(z.string()),
  pixel_shares: z.object({ low: z.number(), medium: z.number(), high: z.number() }),
  raster_url: z.string(),
  png_url: z.string(),
})

export const SourceMask = z.looseObject({
  png_url: z.string(),
  raster_url: z.string(),
  colormap: Colormap,
})

export const Layer = z.looseObject({
  parameter: Parameter,
  source: Source,
  status: Status,
  reason: z.string().nullable(),
  coverage: z.number().optional(),
  unit: z.string().nullable().optional(),
  png_url: z.string().optional(),
  masked_png_url: z.string().optional(), // proposed (UI_BRIEF): colour where high/medium, grey hatch where low
  geotiff_url: z.string().optional(),
  stats: Stats.optional(),
  colormap: Colormap.optional(),
  confidence: Confidence.optional(),
  provenance: z.record(z.string(), z.unknown()).optional(),
  source_mask: SourceMask.optional(),
})

export const Bounds = z.tuple([z.tuple([z.number(), z.number()]), z.tuple([z.number(), z.number()])])

export const FieldResult = z.looseObject({
  id: z.union([z.string(), z.number()]).nullable(),
  matched_plot_id: z.string().nullable(),
  match: Match,
  field_name: z.string().nullable(),
  bounds: Bounds.nullable(),
  layers: z.array(Layer),
})

export const DataAsOf = z.record(z.string(), z.string())

export const LayersResponse = z.looseObject({
  run_id: z.string(),
  data_as_of: DataAsOf,
  fields: z.array(FieldResult),
})

export const RunCurrent = z.looseObject({ run_id: z.string(), data_as_of: DataAsOf })

export const FieldProps = z.looseObject({
  plotId: z.string(),
  name: z.string(),
  area_ha: z.number(),
  state: z.enum(['NI', 'ST']),
  use_for_stats: z.boolean(),
})

// Proposed GET /soil/meta (not in the API contract yet): the DB tables the spec sheet and "about" page need.
export const Meta = z.looseObject({
  run_id: z.string(),
  data_as_of: DataAsOf,
  runs: z.array(z.looseObject({ run_id: z.string(), created_at: z.string(), is_current: z.number(), notes: z.string().nullable().optional() })),
  sources: z.array(
    z.looseObject({
      source: z.string(),
      label: z.string(),
      scale: z.string().nullable(),
      native_resolution_m: z.number().nullable(),
      region: z.string().nullable(),
      licence: z.string().nullable(),
      pulled: z.string().nullable(),
    }),
  ),
  parameters: z.array(z.looseObject({ parameter: z.string(), label: z.string(), description: z.string().nullable() })),
  source_parameters: z.array(z.looseObject({ source: z.string(), parameter: z.string(), method: z.string().nullable() })),
  validation: z.array(
    z.looseObject({ metric: z.string(), scope: z.string(), value: z.number().nullable(), n: z.number().nullable(), details: z.unknown() }),
  ),
})
