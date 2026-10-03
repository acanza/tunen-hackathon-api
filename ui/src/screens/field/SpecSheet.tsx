import { useState } from 'react'
import { formatDate } from '../../domain/format'
import { useMeta } from '../../api/hooks'
import type { Layer, Meta } from '../../api/types'
import { Chip, ConfidenceBadge, Panel } from '../../components/badges'
import { formatInterval, formatValue, statusView } from '../../domain/layers'
import { auditId, farmerSentences } from '../../domain/sentences'
import { validationLines } from '../../domain/validation'
import { auditDriver } from '../../i18n/drivers'
import { DATA_SOURCE_LABEL, PARAM_LABEL, ZONE_TEXT } from '../../i18n/labels'
import { reasonText } from '../../i18n/reasons'
import type { FieldCtx } from './context'

export function SpecSheet({ field, feature, proposed }: FieldCtx) {
  const [view, setView] = useState<'farmer' | 'audit'>('farmer')
  const meta = useMeta()
  const sentences = farmerSentences(field, proposed)
  const rows = field.layers.filter((l) => !statusView(l).hidden)
  const dataAsOf = meta.data?.data_as_of

  const goAudit = (id: string) => {
    setView('audit')
    requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-4 p-4">
        <div className="no-print flex flex-wrap items-center gap-2">
          <div className="inline-flex rounded-md bg-stone-200 p-0.5">
            {(['farmer', 'audit'] as const).map((v) => (
              <button key={v} onClick={() => setView(v)} className={`rounded px-3 py-1 text-sm font-medium ${view === v ? 'bg-white shadow' : 'text-stone-600'}`}>
                {v === 'farmer' ? 'Farmer view' : 'Audit view'}
              </button>
            ))}
          </div>
          <button onClick={() => window.print()} className="ml-auto rounded-md bg-stone-900 px-3 py-1.5 text-sm text-white hover:bg-stone-700">
            Print / PDF (both views)
          </button>
        </div>

        <header>
          <h1 className="text-xl font-semibold">{field.field_name}: soil spec sheet</h1>
          <p className="text-sm text-stone-600">
            {feature && `${feature.properties.area_ha.toFixed(1)} ha · ${feature.properties.state === 'NI' ? 'Lower Saxony' : 'Saxony-Anhalt'} · `}
            Data as of {formatDate(dataAsOf?.sentinel2)}
          </p>
        </header>

        {/* On screen one view at a time; in print both. */}
        <div className={view === 'farmer' ? '' : 'hidden print:block'}>
          <Panel title="In plain words">
            <ol className="space-y-2">
              {sentences.map((s, i) => (
                <li key={s.topic} className="flex gap-2 text-[15px] leading-snug">
                  <span className="w-28 shrink-0 text-sm font-medium text-stone-500">{s.topic}</span>
                  <span>
                    {s.text}{' '}
                    {s.refs.map((r) => (
                      <button
                        key={`${r.parameter}-${r.source}`}
                        onClick={() => goAudit(auditId(r.parameter, r.source))}
                        className="align-super text-xs font-semibold text-emerald-800 hover:underline"
                        title="Show the numbers behind this sentence"
                      >
                        [{i + 1}]
                      </button>
                    ))}
                  </span>
                </li>
              ))}
            </ol>
            <p className="mt-4 text-xs text-stone-500">
              Based on the state soil survey (where available), the global SoilGrids map, our own models and satellite images 2019–2026. Data as of{' '}
              {formatDate(dataAsOf?.sentinel2)}. Every statement links to its row in the audit view.
            </p>
          </Panel>
        </div>

        <div className={view === 'audit' ? 'space-y-4' : 'hidden space-y-4 print:block print-break'}>
          <Panel title="Every layer">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] text-xs">
                <thead className="text-left text-stone-500">
                  <tr className="[&>th]:px-2 [&>th]:py-1 [&>th]:font-medium">
                    <th>#</th>
                    <th>Parameter / source</th>
                    <th>Value</th>
                    <th>90 % range</th>
                    <th>Confidence</th>
                    <th>Drivers</th>
                    <th>Method</th>
                    <th>Coverage / zone</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((l) => (
                    <AuditRow key={`${l.parameter}-${l.source}`} l={l} meta={meta.data} marker={sentences.findIndex((s) => s.refs.some((r) => r.parameter === l.parameter && r.source === l.source))} />
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <SourcesPanel meta={meta.data} />
          <Panel title="Validation">
            <ul className="list-disc space-y-0.5 pl-4 text-xs text-stone-700">
              {validationLines(meta.data).map((v) => (
                <li key={v.key}>{v.audit}</li>
              ))}
            </ul>
          </Panel>
          <Panel title="Run">
            <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5 text-xs">
              <dt className="text-stone-500">run_id</dt>
              <dd className="font-mono">{meta.data?.run_id}</dd>
              {Object.entries(dataAsOf ?? {}).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-stone-500">{DATA_SOURCE_LABEL[k] ?? k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
          </Panel>
        </div>
      </div>
    </div>
  )
}

function AuditRow({ l, meta, marker }: { l: Layer; meta?: Meta; marker: number }) {
  const method = meta?.source_parameters.find((x) => x.source === l.source && x.parameter === l.parameter)?.method
  const sv = statusView(l)
  return (
    <tr id={auditId(l.parameter, l.source)} className="border-t border-stone-100 align-top target:bg-amber-50 [&>td]:px-2 [&>td]:py-1.5">
      <td className="font-semibold text-emerald-800">{marker >= 0 ? `[${marker + 1}]` : ''}</td>
      <td>
        <div className="font-medium">{PARAM_LABEL[l.parameter]}</div>
        <div className="text-stone-500">
          {l.parameter} / {l.source}
        </div>
      </td>
      {sv.disabled ? (
        <td colSpan={6} className="text-stone-600">
          <Chip>{l.status}</Chip> <span className="font-mono">{l.reason}</span>: {reasonText(l.reason)}
        </td>
      ) : (
        <>
          <td className="tabular-nums">{formatValue(l)}</td>
          <td className="tabular-nums">{formatInterval(l)?.replace('likely ', '') ?? '–'}</td>
          <td>{l.confidence && <ConfidenceBadge level={l.confidence.level} compact />}</td>
          <td>
            <ul className="space-y-0.5">
              {l.confidence?.drivers.map((d) => (
                <li key={d}>{auditDriver(d)}</li>
              ))}
            </ul>
          </td>
          <td className="text-stone-600">{method ?? '–'}</td>
          <td className="text-stone-600">
            {l.status === 'partial' && <Chip tone="warn">{Math.round((l.coverage ?? 0) * 100)} %</Chip>} {l.stats && ZONE_TEXT[l.stats.zone]}
          </td>
        </>
      )}
    </tr>
  )
}

const SOURCE_LONG_EN: Record<string, string> = {
  soilgrids: 'SoilGrids global soil map (ISRIC)',
  lbeg_bk50: 'Lower Saxony soil map 1:50 000 (LBEG BK50)',
  lbeg_bodenschaetzung: 'Official soil survey: Lower Saxony (LBEG) + Saxony-Anhalt (LAGB)',
  derived: 'Our model (satellite images 2019–2026)',
  best: 'Best available source per spot',
}

export function SourcesPanel({ meta }: { meta?: Meta }) {
  return (
    <Panel title="Sources">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs">
          <thead className="text-left text-stone-500">
            <tr className="[&>th]:px-2 [&>th]:py-1 [&>th]:font-medium">
              <th>Source</th>
              <th>Scale</th>
              <th>Region</th>
              <th>Licence</th>
              <th>Pulled</th>
            </tr>
          </thead>
          <tbody>
            {meta?.sources.map((s) => (
              <tr key={s.source} className="border-t border-stone-100 [&>td]:px-2 [&>td]:py-1.5">
                <td>
                  <div className="font-medium">{SOURCE_LONG_EN[s.source] ?? s.label}</div>
                  <div className="text-stone-500">{s.label}</div>
                </td>
                <td>{s.scale}</td>
                <td>{s.region}</td>
                <td>{s.licence === 'not verified' ? <Chip tone="warn">Licence not verified</Chip> : s.licence}</td>
                <td>{s.pulled}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
