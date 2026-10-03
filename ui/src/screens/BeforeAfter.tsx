import { useState } from 'react'
import { ImageOverlay } from 'react-leaflet'
import { useNavigate, useParams } from 'react-router-dom'
import { useField, useFields, useProposed } from '../api/hooks'
import type { Source } from '../api/types'
import { ConfidenceBadge, ErrorNote, Loading, Panel, PreviewBadge } from '../components/badges'
import { Legend } from '../components/Legend'
import { SourceShares } from '../components/LayerDetail'
import { sourceLegend } from '../domain/colormap'
import { formatInterval, formatValue, getLayer, hasData, statusView } from '../domain/layers'
import { farmerDrivers } from '../i18n/drivers'
import { PARAM_LABEL, SOURCE_LABEL } from '../i18n/labels'
import { BaseMap } from '../map/BaseMap'
import { FieldOutline } from '../map/FieldOutline'
import { SoilLayerOverlay } from '../map/SoilLayerOverlay'
import { SyncMember, useSyncGroup } from '../map/SyncedMaps'

const DEMO_FIELDS = ['Bocksenden', 'Altenaer Weg', 'Cawi-Wiese', 'Spraken', 'Mittelbreite']
const BEFORE_SOURCES: Record<'bodenzahl' | 'nfk', Source[]> = {
  bodenzahl: ['lbeg_bodenschaetzung', 'derived'],
  nfk: ['soilgrids', 'derived'],
}

export function BeforeAfter() {
  const { plotId: routeId } = useParams()
  const navigate = useNavigate()
  const fields = useFields()
  const demo = DEMO_FIELDS.map((n) => fields.data?.features.find((f) => f.properties.name === n)).filter((f) => !!f)
  const plotId = routeId ?? demo[0]?.properties.plotId
  const feature = fields.data?.features.find((f) => f.properties.plotId === plotId)
  const field = useField(plotId)
  const proposed = useProposed(plotId)
  const [param, setParam] = useState<'bodenzahl' | 'nfk'>('bodenzahl')
  const [step, setStep] = useState<'before' | 'after' | 'conflict'>('before')
  const group = useSyncGroup()

  if (fields.isLoading || field.isLoading) return <Loading />
  if (field.error) return <ErrorNote error={field.error} />
  const f = field.data
  if (!f?.bounds) return <p className="p-6 text-sm">Pick a field.</p>
  const best = getLayer(f, param, 'best')
  const discrepancy = proposed.data?.discrepancy?.find((d) => d.parameter === param)

  return (
    <div className="flex flex-col lg:h-full">
      <div className="no-print flex flex-wrap items-center gap-3 border-b border-stone-200 bg-white px-4 py-2">
        <select
          className="rounded-md border border-stone-300 px-2 py-1 text-sm"
          value={plotId}
          onChange={(e) => navigate(`/demo/before-after/${e.target.value}`)}
        >
          {demo.map((d) => (
            <option key={d.properties.plotId} value={d.properties.plotId}>
              {d.properties.name}
            </option>
          ))}
          {feature && !demo.includes(feature) && <option value={plotId}>{feature.properties.name}</option>}
        </select>
        <Segmented value={param} onChange={setParam} options={[['bodenzahl', 'Soil quality score'], ['nfk', 'Plant-available water']]} />
        <Segmented
          value={step}
          onChange={setStep}
          options={[
            ['before', '1 · Siloed sources'],
            ['after', '2 · Confidence fusion'],
            ['conflict', '3 · Where sources disagree'],
          ]}
        />
      </div>

      {step === 'before' && (
        <div className="grid min-h-0 flex-1 gap-3 overflow-y-auto p-3 md:grid-cols-2">
          {BEFORE_SOURCES[param].map((s) => {
            const l = getLayer(f, param, s)
            const sv = statusView(l)
            return (
              <Panel
                key={s}
                className="flex min-h-[420px] flex-col"
                title={`${PARAM_LABEL[param]} · ${SOURCE_LABEL[s]}`}
                actions={l?.confidence && <ConfidenceBadge level={l.confidence.level} compact />}
              >
                <div className="relative min-h-[300px] flex-1 overflow-hidden rounded-md">
                  <BaseMap bounds={f.bounds!} aerial>
                    <SyncMember group={group} />
                    {hasData(l) && <SoilLayerOverlay layer={l} bounds={f.bounds!} mode="raw" />}
                    <FieldOutline feature={feature} color="#fff" />
                  </BaseMap>
                </div>
                <div className="mt-2 text-sm">
                  {hasData(l) ? (
                    <>
                      <b>{formatValue(l)}</b> <span className="text-stone-500">{formatInterval(l)}</span>
                      {sv.badge && <span className="ml-2 text-amber-800">{sv.badge}</span>}
                      <div className="text-xs text-stone-500">{farmerDrivers(l.confidence.drivers).join(' ')}</div>
                    </>
                  ) : (
                    <span className="text-stone-600">{sv.explanation || 'Not available.'}</span>
                  )}
                </div>
              </Panel>
            )
          })}
          <p className="text-xs text-stone-500 md:col-span-2">
            Each source as delivered (uncertain areas hatched). They tell different, incomplete stories: the official survey may cover only part of
            the field, and SoilGrids water-holding is nearly constant on this sandy farm.
          </p>
        </div>
      )}

      {step === 'after' && hasData(best) && (
        <div className="grid min-h-0 flex-1 lg:grid-cols-[1fr_360px]">
          <div className="relative min-h-[360px]">
            <BaseMap bounds={f.bounds!} aerial>
              <SoilLayerOverlay layer={best} bounds={f.bounds!} />
              {best.source_mask && <ImageOverlay url={best.source_mask.png_url} bounds={f.bounds!} opacity={0.35} className="pixelated" />}
              <FieldOutline feature={feature} color="#fff" />
            </BaseMap>
          </div>
          <aside className="space-y-3 overflow-y-auto border-l border-stone-200 bg-stone-50 p-3">
            <Panel title="One map, and it tells you where it’s sure" actions={<ConfidenceBadge level={best.confidence.level} />}>
              <div className="text-lg font-semibold">{formatValue(best)}</div>
              <div className="text-sm text-stone-600">{formatInterval(best)}</div>
              {best.stats.source_shares && (
                <div className="mt-3">
                  <SourceShares shares={best.stats.source_shares} />
                </div>
              )}
              <ul className="mt-3 list-disc pl-4 text-sm text-stone-700">
                {farmerDrivers(best.confidence.drivers).map((d) => (
                  <li key={d}>{d}</li>
                ))}
              </ul>
            </Panel>
            <Panel title="Legend">
              <Legend colormap={best.colormap} />
              {best.source_mask && (
                <div className="mt-3">
                  <Legend colormap={sourceLegend(best.source_mask.colormap)} masking={false} title="Tint: where each value comes from" />
                </div>
              )}
            </Panel>
          </aside>
        </div>
      )}

      {step === 'conflict' && (
        <div className="mx-auto max-w-2xl p-4">
          <Panel title="Where sources disagree" actions={<PreviewBadge />}>
            {discrepancy ? (
              <>
                <p className="text-sm">
                  <b>{Math.round(discrepancy.stats.share_conflict * 100)} %</b> of the field: {discrepancy.stats.pairs.map((p) => SOURCE_LABEL[p as Source] ?? p).join(' vs ')} disagree
                  by more than their combined uncertainty.
                </p>
                <p className="mt-2 text-sm text-stone-700">{discrepancy.explanation}</p>
              </>
            ) : (
              <p className="text-sm text-stone-600">
                The conflict map (sources disagreeing by more than their combined uncertainty) is still to be produced on the data side.
              </p>
            )}
          </Panel>
        </div>
      )}
    </div>
  )
}

function Segmented<T extends string>({ value, onChange, options }: { value: T; onChange: (v: T) => void; options: Array<[T, string]> }) {
  return (
    <div className="inline-flex rounded-md bg-stone-200 p-0.5">
      {options.map(([v, label]) => (
        <button key={v} onClick={() => onChange(v)} className={`rounded px-2.5 py-1 text-sm font-medium ${value === v ? 'bg-white shadow' : 'text-stone-600'}`}>
          {label}
        </button>
      ))}
    </div>
  )
}

