import { useState } from 'react'
import { ImageOverlay } from 'react-leaflet'
import { Link, useSearchParams } from 'react-router-dom'
import { PARAMETERS } from '../../api/schema'
import type { Parameter, Source } from '../../api/types'
import { Panel } from '../../components/badges'
import { LayerDetail } from '../../components/LayerDetail'
import { Legend } from '../../components/Legend'
import { LayerSwitcher, SourceSwitcher } from '../../components/Switchers'
import { sourceLegend } from '../../domain/colormap'
import { allLow, getLayer, hasData, pickDefaultSource } from '../../domain/layers'
import { BaseMap } from '../../map/BaseMap'
import { FieldOutline } from '../../map/FieldOutline'
import { SoilLayerOverlay, type RenderMode } from '../../map/SoilLayerOverlay'
import type { FieldCtx } from './context'

const PARAMS = PARAMETERS.filter((p) => p !== 'yield_potential') as Parameter[]

export function MapsTab({ field, feature }: FieldCtx) {
  const [sp, setSp] = useSearchParams()
  const param = (sp.get('p') as Parameter) ?? 'bodenzahl'
  const source = (sp.get('s') as Source) ?? pickDefaultSource(field, param)
  const [mode, setMode] = useState<RenderMode>('masked')
  const [showSources, setShowSources] = useState(false)
  const [hover, setHover] = useState<string | null>(null)
  const layer = source ? getLayer(field, param, source) : undefined
  const set = (p: Parameter, s?: Source) => setSp({ p, ...(s ? { s } : {}) }, { replace: true })

  return (
    <div className="grid lg:h-full grid-rows-[auto_minmax(360px,1fr)_auto] lg:grid-cols-[230px_1fr_340px] lg:grid-rows-1">
      <aside className="no-print space-y-4 overflow-y-auto border-r border-stone-200 bg-stone-50 p-3">
        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-stone-500">Layer</h3>
          <LayerSwitcher field={field} params={PARAMS} value={param} onChange={(p) => set(p)} />
        </div>
        <div>
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-stone-500">Source</h3>
          <SourceSwitcher field={field} param={param} value={source} onChange={(s) => set(param, s)} />
        </div>
      </aside>

      <div className="relative min-h-[360px]">
        <BaseMap bounds={field.bounds!} aerial>
          {hasData(layer) && <SoilLayerOverlay key={`${layer.png_url}-${mode}`} layer={layer} bounds={field.bounds!} mode={mode} onHover={setHover} />}
          {showSources && layer?.source_mask && <ImageOverlay url={layer.source_mask.png_url} bounds={field.bounds!} opacity={0.85} className="pixelated" />}
          <FieldOutline feature={feature} color="#fff" />
        </BaseMap>
        <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] max-w-[70%] space-y-2">
          {hasData(layer) && allLow(layer) && mode === 'masked' && (
            <div className="pointer-events-auto rounded-md bg-white/95 p-3 text-sm shadow">
              <b>Public data can’t settle this here.</b> The whole map is uncertain, so we show the range instead of colours.{' '}
              <Link className="text-emerald-800 underline" to={`/field/${field.matched_plot_id}/sampling`}>
                See the sampling plan
              </Link>
              .
            </div>
          )}
          {hover && <div className="rounded-md bg-stone-900/85 px-2 py-1 text-xs text-white">{hover}</div>}
        </div>
      </div>

      <aside className="space-y-3 overflow-y-auto border-l border-stone-200 bg-stone-50 p-3">
        {layer ? (
          <Panel>
            <LayerDetail layer={layer} />
          </Panel>
        ) : (
          <Panel>
            <p className="text-sm text-stone-600">No source provides this value.</p>
          </Panel>
        )}
        {hasData(layer) && (
          <Panel title="Legend">
            <Legend colormap={layer.colormap} />
            <label className="no-print mt-3 flex items-center gap-2 text-xs text-stone-600">
              <input type="checkbox" checked={mode === 'raw'} onChange={(e) => setMode(e.target.checked ? 'raw' : 'masked')} />
              Expert: show colours under uncertain areas (hatched)
            </label>
          </Panel>
        )}
        {layer?.source_mask && (
          <Panel title="Where each value comes from">
            <label className="mb-2 flex items-center gap-2 text-xs text-stone-600">
              <input type="checkbox" checked={showSources} onChange={(e) => setShowSources(e.target.checked)} />
              Show source map
            </label>
            <Legend colormap={sourceLegend(layer.source_mask.colormap)} masking={false} />
          </Panel>
        )}
      </aside>
    </div>
  )
}
