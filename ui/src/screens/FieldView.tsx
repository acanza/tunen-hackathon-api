import { NavLink, useParams } from 'react-router-dom'
import { useField, useFields, useProposed } from '../api/hooks'
import { Chip, ErrorNote, Loading } from '../components/badges'
import { MapsTab } from './field/MapsTab'
import { SamplingTab } from './field/SamplingTab'
import { SignalsTab } from './field/SignalsTab'
import { SpecSheet } from './field/SpecSheet'
import { YieldTab } from './field/YieldTab'

const TABS = [
  { id: 'maps', label: 'Soil maps' },
  { id: 'yield', label: 'Yield pattern' },
  { id: 'sampling', label: 'Sampling plan' },
  { id: 'signals', label: 'Signals & crops' },
  { id: 'sheet', label: 'Spec sheet' },
] as const

export function FieldView() {
  const { plotId, tab = 'maps' } = useParams()
  const field = useField(plotId)
  const fields = useFields()
  const proposed = useProposed(plotId)
  const feature = fields.data?.features.find((f) => f.properties.plotId === plotId)

  if (field.isLoading) return <Loading what="Loading field" />
  if (field.error) return <ErrorNote error={field.error} />
  const f = field.data
  if (!f || f.match === 'outside_coverage_area' || !f.bounds) {
    return <p className="p-6 text-sm">This field isn’t in the farm data.</p>
  }
  const ctx = { field: f, feature, proposed: proposed.data ?? null }

  return (
    <div className="flex flex-col lg:h-full">
      <div className="no-print flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-stone-200 bg-white px-4 pt-2">
        <div className="pb-2">
          <h1 className="text-lg font-semibold leading-tight">{f.field_name}</h1>
          {feature && (
            <div className="flex items-center gap-2 text-xs text-stone-500">
              {feature.properties.area_ha.toFixed(1)} ha
              <Chip tone={feature.properties.state === 'NI' ? 'good' : 'neutral'}>
                {feature.properties.state === 'NI' ? 'Lower Saxony: LBEG survey' : 'Saxony-Anhalt: LAGB survey'}
              </Chip>
              {!feature.properties.use_for_stats && <Chip tone="warn">Narrow field: no satellite history</Chip>}
            </div>
          )}
        </div>
        <nav className="flex gap-1 self-end overflow-x-auto">
          {TABS.map((t) => (
            <NavLink
              key={t.id}
              to={`/field/${plotId}/${t.id}`}
              className={() =>
                `whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium ${tab === t.id ? 'border-stone-900 text-stone-900' : 'border-transparent text-stone-500 hover:text-stone-800'}`
              }
            >
              {t.label}
            </NavLink>
          ))}
        </nav>
      </div>
      <div className="min-h-0 flex-1 lg:overflow-hidden">
        {tab === 'maps' && <MapsTab {...ctx} />}
        {tab === 'yield' && <YieldTab {...ctx} />}
        {tab === 'sampling' && <SamplingTab {...ctx} />}
        {tab === 'signals' && <SignalsTab {...ctx} />}
        {tab === 'sheet' && <SpecSheet {...ctx} />}
      </div>
    </div>
  )
}
