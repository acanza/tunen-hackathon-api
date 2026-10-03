import type { Proposed } from '../../api/proposed'
import type { FieldFeature, FieldResult } from '../../api/types'

export interface FieldCtx {
  field: FieldResult
  feature?: FieldFeature
  proposed: Proposed | null
}
