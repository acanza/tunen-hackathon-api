import { useQuery } from '@tanstack/react-query'
import { ImageOverlay, useMapEvents } from 'react-leaflet'
import type { Bounds, Layer } from '../api/types'
import { DIGITS, fmt, unitSuffix } from '../domain/layers'
import { maskedPng } from './masking'
import { CONF, loadRaster } from './raster'

export type RenderMode = 'masked' | 'raw'

/**
 * One soil layer on the map, following the masking rule. Prefers the data-side `masked_png_url` when it exists;
 * otherwise masks the layer PNG client-side from GeoTIFF band 4. `raw` = expert view: true colours plus the
 * low-confidence hatch PNG on top.
 */
export function SoilLayerOverlay({ layer, bounds, mode = 'masked', opacity = 0.9, onHover }: {
  layer: Layer
  bounds: Bounds
  mode?: RenderMode
  opacity?: number
  onHover?: (text: string | null) => void
}) {
  const raster = useQuery({
    queryKey: ['raster', layer.geotiff_url],
    queryFn: () => loadRaster(layer.geotiff_url!),
    enabled: !!layer.geotiff_url,
    staleTime: Infinity,
  })
  const masked = useQuery({
    queryKey: ['masked', layer.png_url],
    queryFn: () => maskedPng(layer.png_url!, bounds, raster.data!),
    enabled: mode === 'masked' && !layer.masked_png_url && !!raster.data && !!layer.png_url,
    staleTime: Infinity,
  })

  useMapEvents({
    mousemove(e) {
      if (!onHover || !raster.data) return
      const v = raster.data.sample(e.latlng.lat, e.latlng.lng)
      onHover(v ? describePixel(layer, v, mode) : null)
    },
    mouseout() {
      onHover?.(null)
    },
  })

  if (!layer.png_url) return null
  if (mode === 'raw') {
    return (
      <>
        <ImageOverlay url={layer.png_url} bounds={bounds} opacity={opacity} className="pixelated" />
        {layer.confidence?.png_url && <ImageOverlay url={layer.confidence.png_url} bounds={bounds} className="pixelated" />}
      </>
    )
  }
  const url = layer.masked_png_url ?? masked.data
  // Until the masked image is ready, show nothing rather than unmasked colour.
  return url ? <ImageOverlay key={url.slice(-32)} url={url} bounds={bounds} opacity={opacity} className="pixelated" /> : null
}

/** Hover text for one pixel: low pixels give the range and why, never a single value. */
function describePixel(layer: Layer, v: number[], mode: RenderMode = 'masked'): string {
  const [val, lo, hi, conf, src] = v
  const d = DIGITS[layer.parameter]
  const u = unitSuffix(layer.unit)
  const srcCode = layer.source_mask?.colormap.type === 'categorical' ? layer.source_mask.colormap.classes.find((c) => c.value === src)?.code : undefined
  const from = srcCode ? ` · from ${srcCode === 'derived' ? 'our model' : srcCode === 'lbeg_bodenschaetzung' ? 'official survey' : srcCode}` : ''
  if (layer.colormap?.type === 'categorical') {
    const cls = layer.colormap.classes.find((c) => c.value === val)
    return `${cls ? `${cls.code} – ${cls.label}` : '–'}${from}`
  }
  const range = Number.isFinite(lo) && Number.isFinite(hi) ? `likely ${fmt(lo, d)}–${fmt(hi, d)}${u}` : 'range unknown'
  if (conf === CONF.LOW && mode === 'masked') return `Uncertain here: ${range}${from}`
  const word = conf === CONF.HIGH ? 'high' : conf === CONF.MEDIUM ? 'medium' : 'low'
  return `${fmt(val, d)}${u} (${range}, ${word} confidence)${from}`
}
