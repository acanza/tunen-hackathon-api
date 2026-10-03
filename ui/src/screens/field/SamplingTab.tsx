import L from 'leaflet'
import { Marker, Tooltip } from 'react-leaflet'
import { Chip, Panel, PreviewBadge } from '../../components/badges'
import { samplingCsv, samplingGpx, download } from '../../domain/export'
import { getLayer, hasData } from '../../domain/layers'
import { BaseMap } from '../../map/BaseMap'
import { FieldOutline } from '../../map/FieldOutline'
import { SoilLayerOverlay } from '../../map/SoilLayerOverlay'
import type { FieldCtx } from './context'

const numberIcon = (n: number) =>
  L.divIcon({
    className: '',
    html: `<div style="width:26px;height:26px;border-radius:50%;background:#1c1917;color:#fff;font:600 13px/26px system-ui;text-align:center;border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.4)">${n}</div>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })

export function SamplingTab({ field, feature, proposed }: FieldCtx) {
  const plan = proposed?.sampling_plan
  const ph = getLayer(field, 'ph', 'soilgrids')
  const name = field.field_name ?? field.matched_plot_id ?? 'field'
  const slug = name.replace(/[^\w-]+/g, '_')

  return (
    <div className="grid lg:h-full grid-rows-[minmax(360px,1fr)_auto] lg:grid-cols-[1fr_400px] lg:grid-rows-1">
      <div className="min-h-[360px]">
        <BaseMap bounds={field.bounds!} aerial>
          {hasData(ph) && <SoilLayerOverlay layer={ph} bounds={field.bounds!} opacity={0.6} />}
          <FieldOutline feature={feature} color="#fff" />
          {plan?.points.map((p) => (
            <Marker key={p.rank} position={[p.lat, p.lon]} icon={numberIcon(p.rank)}>
              <Tooltip>{p.why}</Tooltip>
            </Marker>
          ))}
        </BaseMap>
      </div>
      <aside className="space-y-3 overflow-y-auto border-l border-stone-200 bg-stone-50 p-3">
        <Panel title="Where to take soil samples" actions={<PreviewBadge />}>
          <p className="text-sm text-stone-700">
            We pick the spots where one lab result could change a decision, not just where the map varies most. For liming: where the pH
            estimate is closest to a coin flip around the threshold.
          </p>
          {!plan ? (
            <p className="mt-3 rounded-md bg-stone-100 p-3 text-sm text-stone-600">No sampling plan for this field yet. The data side hasn’t produced sampling plans; the demo fields have a mock one.</p>
          ) : (
            <>
              <ol className="mt-3 space-y-2">
                {plan.points.map((p) => (
                  <li key={p.rank} className="flex gap-2 text-sm">
                    <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-stone-900 text-xs font-semibold text-white">{p.rank}</span>
                    <div>
                      <div>{p.why}</div>
                      <div className="mt-0.5 flex flex-wrap gap-1 text-xs text-stone-500">
                        <Chip>{p.decision}</Chip>
                        <Chip>
                          estimate {p.current_estimate}, likely {p.interval_90[0]}–{p.interval_90[1]}
                        </Chip>
                        <Chip tone={p.decision_uncertainty > 0.8 ? 'warn' : 'neutral'}>
                          {p.decision_uncertainty > 0.8 ? 'coin flip' : 'leaning'} ({Math.round(p.decision_uncertainty * 100)} %)
                        </Chip>
                      </div>
                      <div className="mt-0.5 font-mono text-xs text-stone-500">
                        {p.lat.toFixed(5)}, {p.lon.toFixed(5)}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
              <p className="mt-3 text-xs text-stone-500">
                Rules: at least {plan.rules.min_spacing_m} m apart, {plan.rules.edge_buffer_m} m from the edge, at most {plan.rules.max_points} points. Covers{' '}
                {plan.covers_ha} ha.
              </p>
              <div className="no-print mt-3 flex flex-wrap gap-2">
                <button className="rounded-md bg-stone-900 px-3 py-1.5 text-sm text-white hover:bg-stone-700" onClick={() => download(`${slug}_samples.gpx`, samplingGpx(name, plan.points), 'application/gpx+xml')}>
                  Download GPX
                </button>
                <button className="rounded-md bg-white px-3 py-1.5 text-sm ring-1 ring-stone-300 hover:bg-stone-100" onClick={() => download(`${slug}_samples.csv`, samplingCsv(name, plan.points), 'text/csv')}>
                  Download CSV
                </button>
                <button disabled className="cursor-not-allowed rounded-md bg-stone-100 px-3 py-1.5 text-sm text-stone-400 ring-1 ring-stone-200" title="Coming later: lab results will recalibrate the maps on the next data run.">
                  Upload lab results
                </button>
              </div>
            </>
          )}
        </Panel>
      </aside>
    </div>
  )
}
