import type { PathOptions } from 'leaflet'
import { useMemo, useState } from 'react'
import { GeoJSON } from 'react-leaflet'
import { Link, useNavigate } from 'react-router-dom'
import { useFarmLayers, useFields } from '../api/hooks'
import type { FieldFeature, FieldResult, Parameter } from '../api/types'
import { ErrorNote, Loading, Panel } from '../components/badges'
import { Legend } from '../components/Legend'
import { colorAt, rgbaCss } from '../domain/colormap'
import { formatInterval, formatValue, getLayer, hasData, pickDefaultSource } from '../domain/layers'
import { PARAM_LABEL, SOURCE_LABEL } from '../i18n/labels'
import { BaseMap } from '../map/BaseMap'

type ColourBy = 'state' | Parameter
const STATE_STYLE = {
  NI: { color: '#1b7837', fillColor: '#5aae61', label: 'Lower Saxony: survey from LBEG (with soil score)' },
  ST: { color: '#7b3294', fillColor: '#c2a5cf', label: 'Saxony-Anhalt: survey from LAGB (soil class only)' },
}
const OPTIONS: ColourBy[] = ['state', 'bodenzahl', 'nfk', 'ph', 'soc', 'texture']

export function Overview() {
  const fields = useFields()
  const [colourBy, setColourBy] = useState<ColourBy>('state')
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const plotIds = useMemo(() => fields.data?.features.map((f) => f.properties.plotId), [fields.data])
  const farm = useFarmLayers(colourBy === 'state' ? undefined : plotIds)
  const byId = useMemo(() => new Map(farm.data?.fields.map((f) => [f.matched_plot_id!, f])), [farm.data])

  if (fields.isLoading) return <Loading what="Loading fields" />
  if (fields.error) return <ErrorNote error={fields.error} />
  const feats = fields.data!.features
  const ha = feats.reduce((s, f) => s + f.properties.area_ha, 0)
  const ni = feats.filter((f) => f.properties.state === 'NI').length
  const shown = feats.filter((f) => f.properties.name.toLowerCase().includes(query.toLowerCase()))
  const sampleLayer = colourBy !== 'state' ? firstLayerWithData(farm.data?.fields, colourBy) : undefined

  const style = (f?: FieldFeature): PathOptions => {
    if (!f) return {}
    if (colourBy === 'state') {
      const s = STATE_STYLE[f.properties.state]
      return { color: s.color, fillColor: s.fillColor, fillOpacity: 0.6, weight: 1.5 }
    }
    const l = fieldLayer(byId.get(f.properties.plotId), colourBy)
    if (!l?.stats || !l.colormap) return { color: '#78716c', fillColor: '#e7e5e4', fillOpacity: 0.5, weight: 1, dashArray: '3 3' }
    // Masking rule at field level: low confidence → grey, dashed; no value colour.
    if (l.confidence?.level === 'low') return { color: '#525252', fillColor: '#bdbdbd', fillOpacity: 0.75, weight: 1.5, dashArray: '4 3' }
    const v = l.colormap.type === 'categorical' ? l.colormap.classes.find((c) => c.code === l.stats!.dominant)?.value ?? NaN : l.stats.mean ?? NaN
    const c = colorAt(l.colormap, v)
    return { color: '#44403c', fillColor: c ? rgbaCss(c) : '#e7e5e4', fillOpacity: 0.85, weight: 1 }
  }

  return (
    <div className="grid lg:h-full grid-rows-[minmax(320px,1fr)_auto] lg:grid-cols-[1fr_360px] lg:grid-rows-1">
      <div className="relative min-h-[320px]">
        <BaseMap bounds={boundsOf(feats)}>
          <GeoJSON
            key={`${colourBy}-${farm.dataUpdatedAt}`}
            data={fields.data!}
            style={style as never}
            onEachFeature={(f: FieldFeature, layer) => {
              layer.on('click', () => navigate(`/field/${f.properties.plotId}`))
              layer.bindTooltip(tooltipHtml(f, byId.get(f.properties.plotId), colourBy), { sticky: true })
            }}
          />
        </BaseMap>
      </div>
      <aside className="space-y-3 overflow-y-auto border-l border-stone-200 bg-stone-50 p-4">
        <Panel title="LuF Seggerde">
          <p className="text-sm text-stone-700">
            <b>{feats.length} fields</b>, {Math.round(ha)} ha. <b>{ni}</b> in Lower Saxony, <b>{feats.length - ni}</b> in Saxony-Anhalt.
          </p>
          <p className="mt-2 text-xs text-stone-500">The farm straddles a state border: two survey portals, two data models. Lower Saxony publishes the soil quality score; Saxony-Anhalt only the soil class, so its score is estimated.</p>
        </Panel>
        <Panel title="Colour fields by">
          <div className="flex flex-wrap gap-1.5">
            {OPTIONS.map((o) => (
              <button
                key={o}
                onClick={() => setColourBy(o)}
                className={`rounded-md px-2 py-1 text-xs font-medium ring-1 ring-inset ${colourBy === o ? 'bg-stone-900 text-white ring-stone-900' : 'bg-white text-stone-700 ring-stone-300 hover:bg-stone-100'}`}
              >
                {o === 'state' ? 'Survey source' : PARAM_LABEL[o]}
              </button>
            ))}
          </div>
          <div className="mt-3">
            {colourBy === 'state' ? (
              <ul className="space-y-1 text-xs">
                {Object.values(STATE_STYLE).map((s) => (
                  <li key={s.label} className="flex items-center gap-2">
                    <span className="h-3 w-3 rounded-sm" style={{ background: s.fillColor, outline: `1.5px solid ${s.color}` }} />
                    {s.label}
                  </li>
                ))}
              </ul>
            ) : farm.isLoading ? (
              <Loading what="Loading field statistics" />
            ) : sampleLayer?.colormap ? (
              <>
                <p className="mb-2 text-xs text-stone-500">Field average, {colourBy === 'texture' ? 'official survey class (LBEG / LAGB)' : 'best available source'}. Grey = public data can’t settle it for that field.</p>
                <Legend colormap={sampleLayer.colormap} />
              </>
            ) : null}
          </div>
        </Panel>
        <Panel title="Fields">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name"
            className="mb-2 w-full rounded-md border border-stone-300 px-2 py-1 text-sm"
          />
          <ul className="max-h-80 divide-y divide-stone-100 overflow-y-auto text-sm">
            {shown.map((f) => (
              <li key={f.properties.plotId}>
                <Link to={`/field/${f.properties.plotId}`} className="flex items-center justify-between py-1.5 hover:text-emerald-800">
                  <span>{f.properties.name}</span>
                  <span className="text-xs text-stone-500">
                    {f.properties.area_ha.toFixed(1)} ha · {f.properties.state}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      </aside>
    </div>
  )
}

function fieldLayer(r: FieldResult | undefined, p: Parameter) {
  const s = pickDefaultSource(r, p)
  const l = s ? getLayer(r, p, s) : undefined
  return hasData(l) ? l : undefined
}

function firstLayerWithData(fields: FieldResult[] | undefined, p: Parameter) {
  for (const f of fields ?? []) {
    const l = fieldLayer(f, p)
    if (l && (p !== 'texture' || l.colormap?.type === 'categorical')) return l // texture: survey classes now cover both states
  }
  return fields?.map((f) => fieldLayer(f, p)).find(Boolean)
}

const esc = (t: string) => t.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`)

function tooltipHtml(f: FieldFeature, result: FieldResult | undefined, colourBy: ColourBy): string {
  const p = f.properties
  const lines = [`<b>${esc(p.name)}</b>`, `${p.area_ha.toFixed(1)} ha · ${esc(STATE_STYLE[p.state].label)}`]
  const l = colourBy === 'state' ? undefined : fieldLayer(result, colourBy)
  if (l) {
    const value = l.confidence?.level === 'low' ? `Uncertain: ${formatInterval(l) ?? 'range unknown'}` : formatValue(l)
    lines.push(`${esc(PARAM_LABEL[l.parameter])}: ${esc(value)} <span style="color:#78716c">(${esc(SOURCE_LABEL[l.source])}, ${l.confidence?.level ?? '?'} confidence)</span>`)
  }
  lines.push('<span style="color:#78716c">Click to open</span>')
  return lines.join('<br>')
}

function boundsOf(feats: FieldFeature[]): [[number, number], [number, number]] | undefined {
  let s = 90, w = 180, n = -90, e = -180
  const visit = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === 'number') {
      const [x, y] = c as number[]
      s = Math.min(s, y); n = Math.max(n, y); w = Math.min(w, x); e = Math.max(e, x)
    } else if (Array.isArray(c)) c.forEach(visit)
  }
  feats.forEach((f) => 'coordinates' in f.geometry && visit(f.geometry.coordinates))
  return s <= n ? [[s, w], [n, e]] : undefined
}
