import type { Feature, FeatureCollection, Geometry } from 'geojson'
import type { z } from 'zod'
import type * as S from './schema'

export type Parameter = z.infer<typeof S.Parameter>
export type Source = z.infer<typeof S.Source>
export type Status = z.infer<typeof S.Status>
export type Level = z.infer<typeof S.Level>
export type Colormap = z.infer<typeof S.Colormap>
export type CategoricalClass = z.infer<typeof S.CategoricalClass>
export type Stats = z.infer<typeof S.Stats>
export type Confidence = z.infer<typeof S.Confidence>
export type Layer = z.infer<typeof S.Layer>
export type Bounds = z.infer<typeof S.Bounds>
export type FieldResult = z.infer<typeof S.FieldResult>
export type LayersResponse = z.infer<typeof S.LayersResponse>
export type RunCurrent = z.infer<typeof S.RunCurrent>
export type FieldProps = z.infer<typeof S.FieldProps>
export type Meta = z.infer<typeof S.Meta>

export type FieldFeature = Feature<Geometry, FieldProps>
export type FieldCollection = FeatureCollection<Geometry, FieldProps>

/** POST /soil/layers body: a FeatureCollection plus optional parameters/sources (all when omitted). */
export interface LayersRequest {
  type: 'FeatureCollection'
  features: Array<{ type: 'Feature'; id?: string | number; properties: { plotId?: string } & Record<string, unknown>; geometry: Geometry | null }>
  parameters?: Parameter[]
  sources?: Source[]
}
