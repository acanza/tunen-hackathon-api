import { GeoJSON } from 'react-leaflet'
import type { FieldFeature } from '../api/types'

export function FieldOutline({ feature, color = '#1c1917' }: { feature?: FieldFeature; color?: string }) {
  if (!feature) return null
  return <GeoJSON key={feature.properties.plotId} data={feature} interactive={false} style={{ color, weight: 2, fill: false }} />
}
