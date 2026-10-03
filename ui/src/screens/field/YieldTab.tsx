import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useMeta } from '../../api/hooks'
import { ConfidenceBadge, Panel, PreviewBadge } from '../../components/badges'
import { Legend } from '../../components/Legend'
import { farmerDrivers } from '../../i18n/drivers'
import { getLayer, hasData } from '../../domain/layers'
import { validationLines } from '../../domain/validation'
import { fieldTotal, spreadSentences, yieldZones } from '../../domain/yield'
import { BaseMap } from '../../map/BaseMap'
import { FieldOutline } from '../../map/FieldOutline'
import { loadRaster } from '../../map/raster'
import { SoilLayerOverlay } from '../../map/SoilLayerOverlay'
import type { FieldCtx } from './context'

export function YieldTab({ field, feature, proposed }: FieldCtx) {
  const layer = getLayer(field, 'yield_potential', 'derived')
  const meta = useMeta()
  const [usual, setUsual] = useState('7.5')
  const [hover, setHover] = useState<string | null>(null)
  const raster = useQuery({
    queryKey: ['raster', layer?.geotiff_url],
    queryFn: () => loadRaster(layer!.geotiff_url!),
    enabled: !!layer?.geotiff_url,
    staleTime: Infinity,
  })
  if (!hasData(layer)) return <p className="p-6 text-sm">No yield pattern for this field.</p>

  const t = Number(usual.replace(',', '.'))
  const valid = Number.isFinite(t) && t > 0
  const zones = raster.data && valid ? yieldZones(raster.data.values(1), t) : []
  const meanIdx = raster.data ? avg(raster.data.values(1)) : layer.stats.mean ?? 100
  const area = feature?.properties.area_ha
  const rank = proposed?.field_summary

  return (
    <div className="grid lg:h-full grid-rows-[minmax(360px,1fr)_auto] lg:grid-cols-[1fr_400px] lg:grid-rows-1">
      <div className="relative min-h-[360px]">
        <BaseMap bounds={field.bounds!} aerial>
          <SoilLayerOverlay layer={layer} bounds={field.bounds!} onHover={setHover} />
          <FieldOutline feature={feature} color="#fff" />
        </BaseMap>
        {hover && <div className="pointer-events-none absolute bottom-3 left-3 z-[1000] rounded-md bg-stone-900/85 px-2 py-1 text-xs text-white">{hover}</div>}
      </div>
      <aside className="space-y-3 overflow-y-auto border-l border-stone-200 bg-stone-50 p-3">
        <Panel title="Yield pattern within this field" actions={<ConfidenceBadge level={layer.confidence.level} />}>
          <p className="text-sm text-stone-700">
            Relative to <b>this field’s own average (= 100)</b>, from 8 years of satellite images. It shows where the field is consistently
            stronger or weaker; it is not tonnes per hectare and doesn’t compare fields.
          </p>
          <ul className="mt-2 list-disc space-y-0.5 pl-4 text-sm text-stone-700">
            {spreadSentences(layer.stats.p10, layer.stats.p90).map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          <ul className="mt-2 space-y-0.5 text-xs text-stone-500">
            {farmerDrivers(layer.confidence.drivers).map((d) => (
              <li key={d}>· {d}</li>
            ))}
          </ul>
          <div className="mt-3">
            <Legend colormap={layer.colormap} />
          </div>
        </Panel>

        <Panel title="Your expected yield">
          <label className="flex items-center gap-2 text-sm">
            Your usual yield on this field
            <input
              inputMode="decimal"
              value={usual}
              onChange={(e) => setUsual(e.target.value)}
              className="w-20 rounded-md border border-stone-300 px-2 py-1 text-right tabular-nums"
              aria-label="Usual yield in tonnes per hectare"
            />
            t/ha
          </label>
          <p className="mt-1 text-xs text-stone-500">You supply the level, we supply the pattern: expected = your yield × index ÷ 100.</p>
          {valid && zones.length > 0 && (
            <table className="mt-3 w-full text-sm">
              <thead className="text-left text-xs text-stone-500">
                <tr>
                  <th className="font-medium">Zone</th>
                  <th className="text-right font-medium">Share</th>
                  <th className="text-right font-medium">Expected</th>
                </tr>
              </thead>
              <tbody className="tabular-nums">
                {zones.map((z) => (
                  <tr key={z.label} className="border-t border-stone-100">
                    <td className="py-1">{z.label}</td>
                    <td className="text-right">{Math.round(z.share * 100)} %</td>
                    <td className="text-right">{Number.isFinite(z.tPerHa) ? `${z.tPerHa.toFixed(1)} t/ha` : '–'}</td>
                  </tr>
                ))}
              </tbody>
              {area && (
                <tfoot>
                  <tr className="border-t border-stone-300 font-semibold">
                    <td className="py-1">Whole field ({area.toFixed(1)} ha)</td>
                    <td />
                    <td className="text-right tabular-nums">{fieldTotal(t, meanIdx, area).toFixed(0)} t</td>
                  </tr>
                </tfoot>
              )}
            </table>
          )}
          {layer.confidence.level === 'low' && (
            <p className="mt-2 rounded-md bg-stone-100 p-2 text-xs text-stone-700">The pattern on this field is uncertain; treat the zones as a rough guide.</p>
          )}
        </Panel>

        <Panel title="How we know">
          <ul className="list-disc space-y-1 pl-4 text-sm text-stone-700">
            {validationLines(meta.data, 'yield').map((v) => (
              <li key={v.key}>{v.text}</li>
            ))}
            <li>Not yet checked against harvest data (none available).</li>
          </ul>
        </Panel>

        <Panel title="Compared with the farm’s other fields" actions={<PreviewBadge />}>
          {rank ? (
            <p className="text-sm text-stone-700">
              Over {rank.seasons} seasons this field ranked, on average, above <b>{rank.productivity_rank_pct} %</b> of the farm’s fields.{' '}
              <span className="text-stone-500">({rank.note})</span>
            </p>
          ) : (
            <p className="text-sm text-stone-500">Not available yet: the between-field rank is still to be produced on the data side.</p>
          )}
        </Panel>
      </aside>
    </div>
  )
}

const avg = (v: number[]) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : 100)
