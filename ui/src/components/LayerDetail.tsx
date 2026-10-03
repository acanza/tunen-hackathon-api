import type { Layer } from '../api/types'
import { DIGITS, fmt, formatInterval, formatValue, statusView, unitSuffix } from '../domain/layers'
import { auditDriver, farmerDrivers } from '../i18n/drivers'
import { PARAM_DEPTH, PARAM_LABEL, SOURCE_COLOR, SOURCE_LABEL, ZONE_TEXT } from '../i18n/labels'
import { Chip, ConfidenceBadge } from './badges'

/** Side panel for one layer: value, range, confidence with reasons, coverage, stats zone. */
export function LayerDetail({ layer, audit = false }: { layer: Layer; audit?: boolean }) {
  const sv = statusView(layer)
  const s = layer.stats
  const c = layer.confidence
  const d = DIGITS[layer.parameter]
  const u = unitSuffix(layer.unit)
  const low = c?.level === 'low'
  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="text-xs uppercase tracking-wide text-stone-500">
          {PARAM_LABEL[layer.parameter]} · {SOURCE_LABEL[layer.source]}
        </div>
        <div className="text-xs text-stone-500">{PARAM_DEPTH[layer.parameter]}</div>
      </div>
      {sv.disabled ? (
        <p className="rounded-md bg-stone-100 p-3 text-stone-700">
          <b>Not available.</b> {sv.explanation}
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {c && <ConfidenceBadge level={c.level} />}
            {sv.badge && (
              <Chip tone="warn" title={sv.explanation}>
                {sv.badge}
              </Chip>
            )}
          </div>
          {/* Low confidence: lead with the range, not the single value. */}
          <div>
            {low && formatInterval(layer) ? (
              <>
                <div className="text-lg font-semibold">{capitalise(formatInterval(layer)!)}</div>
                <div className="text-xs text-stone-500">Field average estimate {formatValue(layer)}; too uncertain to rely on.</div>
              </>
            ) : (
              <>
                <div className="text-lg font-semibold">{formatValue(layer)}</div>
                {formatInterval(layer) && <div className="text-stone-600">{formatInterval(layer)} (90 % range)</div>}
              </>
            )}
            {s?.p10 != null && s.p90 != null && layer.colormap?.type !== 'categorical' && (
              <div className="text-xs text-stone-500">
                Across the field: {fmt(s.p10, d)}–{fmt(s.p90, d)}
                {u} (10th–90th percentile)
              </div>
            )}
            {s?.classes && (
              <div className="mt-1 flex flex-wrap gap-1">
                {Object.entries(s.classes).map(([k, v]) => (
                  <Chip key={k}>
                    {k} {Math.round(v * 100)} %
                  </Chip>
                ))}
              </div>
            )}
          </div>
          {s?.source_shares && <SourceShares shares={s.source_shares} />}
          {c && c.drivers.length > 0 && (
            <div>
              <div className="mb-1 text-xs font-medium text-stone-600">{audit ? 'Confidence drivers' : 'Why this confidence'}</div>
              <ul className="list-disc space-y-0.5 pl-4 text-stone-700">
                {(audit ? c.drivers.map(auditDriver) : farmerDrivers(c.drivers)).map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </div>
          )}
          {s && <p className="text-xs text-stone-500">{ZONE_TEXT[s.zone]}</p>}
        </>
      )}
    </div>
  )
}

export function SourceShares({ shares }: { shares: Record<string, number> }) {
  const entries = Object.entries(shares).sort((a, b) => b[1] - a[1])
  return (
    <div>
      <div className="flex h-2.5 overflow-hidden rounded-full ring-1 ring-black/10">
        {entries.map(([k, v]) => (
          <div key={k} style={{ width: `${v * 100}%`, background: SOURCE_COLOR[k] ?? '#999' }} title={k} />
        ))}
      </div>
      <p className="mt-1 text-xs text-stone-600">
        {entries.map(([k, v]) => `${Math.round(v * 100)} % ${k === 'derived' ? 'our model' : k === 'lbeg_bodenschaetzung' ? 'official survey' : (SOURCE_LABEL as Record<string, string>)[k] ?? k}`).join(', ')}
      </p>
    </div>
  )
}

const capitalise = (t: string) => t[0].toUpperCase() + t.slice(1)
