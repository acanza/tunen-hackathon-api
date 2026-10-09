import { formatDate } from '../domain/format'
import { useMeta } from '../api/hooks'
import { ErrorNote, Loading, Panel } from '../components/badges'
import { validationLines } from '../domain/validation'
import { DATA_SOURCE_LABEL, PARAM_LABEL } from '../i18n/labels'
import type { Parameter } from '../api/types'
import { SourcesPanel } from './field/SpecSheet'

export function About() {
  const meta = useMeta()
  if (meta.isLoading) return <Loading />
  if (meta.error) return <ErrorNote error={meta.error} />
  const m = meta.data!
  const run = m.runs.find((r) => r.is_current)
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl space-y-4 p-4">
        <h1 className="text-xl font-semibold">About the data</h1>
        <Panel title="This run">
          <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-stone-500">Run</dt>
            <dd className="font-mono">{m.run_id}</dd>
            <dt className="text-stone-500">Built</dt>
            <dd>{formatDate(run?.created_at)}</dd>
            {Object.entries(m.data_as_of).map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-stone-500">{DATA_SOURCE_LABEL[k] ?? k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
            {run?.notes && (
              <>
                <dt className="text-stone-500">Notes</dt>
                <dd>{run.notes}</dd>
              </>
            )}
          </dl>
        </Panel>
        <SourcesPanel meta={m} />
        <Panel title="How each value is made">
          <table className="w-full text-xs">
            <thead className="text-left text-stone-500">
              <tr className="[&>th]:px-2 [&>th]:py-1 [&>th]:font-medium">
                <th>Value</th>
                <th>Source</th>
                <th>Method</th>
              </tr>
            </thead>
            <tbody>
              {m.source_parameters.map((sp) => (
                <tr key={`${sp.source}-${sp.parameter}`} className="border-t border-stone-100 [&>td]:px-2 [&>td]:py-1.5">
                  <td className="font-medium">{PARAM_LABEL[sp.parameter as Parameter] ?? sp.parameter}</td>
                  <td>{sp.source}</td>
                  <td className="text-stone-600">{sp.method}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
        <Panel title="How well it works">
          <ul className="list-disc space-y-1 pl-4 text-sm text-stone-700">
            {validationLines(m).map((v) => (
              <li key={v.key}>
                {v.text} <span className="text-xs text-stone-500">({v.audit})</span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  )
}
