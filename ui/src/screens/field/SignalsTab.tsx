import type { Keyword, Rating } from '../../api/proposed'
import { Chip, Panel, PreviewBadge } from '../../components/badges'
import type { FieldCtx } from './context'

const SIGNAL_LABEL: Record<string, string> = {
  liming: 'Liming',
  drought_risk: 'Drought risk',
  erosion: 'Erosion',
  compaction: 'Compaction',
  nitrate_leaching: 'Nitrate leaching',
}
const SIGNAL_ICON: Record<string, string> = { liming: '⚗', drought_risk: '☀', erosion: '≋', compaction: '▤', nitrate_leaching: '↓' }
const KEYWORD_TONE: Record<Keyword, 'bad' | 'warn' | 'neutral' | 'good' | 'info'> = {
  Probable: 'bad',
  Possible: 'warn',
  Unlikely: 'neutral',
  No: 'good',
  Unknown: 'info',
}
const RATING_TONE: Record<Rating, 'good' | 'warn' | 'bad'> = { 'Well adapted': 'good', 'With limitations': 'warn', 'Poorly adapted': 'bad' }
const RATING_ICON: Record<Rating, string> = { 'Well adapted': '✓', 'With limitations': '!', 'Poorly adapted': '✕' }

const CROP_LABEL: Record<string, string> = {
  winter_wheat: 'Wheat', wheat: 'Wheat', barley: 'Barley', rye: 'Rye', rapeseed: 'Rapeseed', maize: 'Maize', sugar_beet: 'Sugar beet', potato: 'Potato', grassland: 'Grassland',
}
const FACTOR_TEXT: Record<string, string> = {
  low_available_water: 'low available water',
  low_fertility: 'low soil fertility',
  low_ph: 'low pH',
  high_ph: 'high pH',
  heavy_soil: 'heavy soil',
  light_soil: 'light sandy soil',
  waterlogging: 'waterlogging',
  spring_drought: 'dry springs',
}

export function SignalsTab({ proposed }: FieldCtx) {
  const signals = proposed?.signals
  const crops = proposed?.crop_suitability
  return (
    <div className="mx-auto max-w-4xl space-y-4 overflow-y-auto p-4">
      <Panel title="Management signals" actions={<PreviewBadge />}>
        <p className="mb-3 text-xs text-stone-500">One word per signal. No doses, rates or products.</p>
        {signals ? (
          <ul className="divide-y divide-stone-100">
            {signals.map((s) => (
              <li key={s.signal} className="flex items-start gap-3 py-2">
                <span className="w-6 text-center text-lg" aria-hidden>
                  {SIGNAL_ICON[s.signal]}
                </span>
                <div className="w-36 shrink-0 text-sm font-medium">{SIGNAL_LABEL[s.signal] ?? s.signal}</div>
                <div className="w-24 shrink-0">
                  <Chip tone={KEYWORD_TONE[s.keyword]}>{s.keyword}</Chip>
                </div>
                <div className="text-sm text-stone-700">
                  {s.farmer_text}
                  <details className="mt-0.5 text-xs text-stone-500">
                    <summary className="cursor-pointer">How we decided</summary>
                    <div>Rule: {s.audit.rule}</div>
                    <div>
                      Inputs:{' '}
                      {Object.entries(s.audit.inputs)
                        .map(([k, v]) => `${k} = ${v}`)
                        .join(', ')}
                    </div>
                  </details>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <NotYet />
        )}
      </Panel>

      <Panel title="Crop suitability" actions={<PreviewBadge />}>
        {crops ? (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-stone-500">
              <tr>
                <th className="py-1 font-medium">Crop</th>
                <th className="font-medium">Rating</th>
                <th className="font-medium">Limiting factor</th>
              </tr>
            </thead>
            <tbody>
              {crops.map((c) => (
                <tr key={c.crop} className="border-t border-stone-100">
                  <td className="py-1.5 font-medium">{CROP_LABEL[c.crop] ?? c.crop}</td>
                  <td>
                    <Chip tone={RATING_TONE[c.rating]}>
                      <span aria-hidden>{RATING_ICON[c.rating]}</span> {c.rating}
                    </Chip>
                  </td>
                  <td className="text-stone-700">
                    {c.limiting_factors.length ? c.limiting_factors.map((f) => FACTOR_TEXT[f] ?? f.replace(/_/g, ' ')).join(', ') : <span className="text-stone-500">None</span>}
                    {c.confidence === 'low' && <span className="text-stone-500"> (uncertain: based on coarse data)</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <NotYet />
        )}
      </Panel>
    </div>
  )
}

const NotYet = () => (
  <p className="rounded-md bg-stone-100 p-3 text-sm text-stone-600">Not available for this field yet. The data side hasn’t produced this; the demo fields have mock values.</p>
)
