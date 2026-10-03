import type { FieldResult, Parameter, Source } from '../api/types'
import { hasData, statusView } from '../domain/layers'
import { PARAM_LABEL, SOURCE_LABEL } from '../i18n/labels'
import { ConfidenceBadge } from './badges'

const btn = (active: boolean, disabled = false) =>
  `w-full rounded-md px-2.5 py-1.5 text-left text-sm ring-1 ring-inset ${
    disabled ? 'cursor-not-allowed bg-stone-100 text-stone-400 ring-stone-200' : active ? 'bg-stone-900 text-white ring-stone-900' : 'bg-white text-stone-800 ring-stone-300 hover:bg-stone-100'
  }`

export function LayerSwitcher({ field, params, value, onChange }: { field: FieldResult; params: Parameter[]; value: Parameter; onChange: (p: Parameter) => void }) {
  return (
    <ul className="space-y-1">
      {params.map((p) => {
        const any = field.layers.some((l) => l.parameter === p && hasData(l))
        return (
          <li key={p}>
            <button className={btn(p === value, !any)} disabled={!any} onClick={() => onChange(p)} title={any ? undefined : 'No source has this value for this field.'}>
              {PARAM_LABEL[p]}
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export function SourceSwitcher({ field, param, value, onChange }: { field: FieldResult; param: Parameter; value?: Source; onChange: (s: Source) => void }) {
  const layers = field.layers.filter((l) => l.parameter === param && !statusView(l).hidden)
  return (
    <ul className="space-y-1">
      {layers.map((l) => {
        const sv = statusView(l)
        return (
          <li key={l.source}>
            <button className={btn(l.source === value, sv.disabled)} disabled={sv.disabled} onClick={() => onChange(l.source)} title={sv.explanation}>
              <span className="flex items-center justify-between gap-2">
                <span>{SOURCE_LABEL[l.source]}</span>
                {l.confidence && <ConfidenceBadge level={l.confidence.level} compact />}
              </span>
              {sv.disabled && <span className="mt-0.5 block text-xs text-stone-500">{sv.explanation}</span>}
              {!sv.disabled && sv.badge && <span className={`mt-0.5 block text-xs ${l.source === value ? 'text-stone-300' : 'text-amber-800'}`}>{sv.badge}</span>}
            </button>
          </li>
        )
      })}
    </ul>
  )
}
