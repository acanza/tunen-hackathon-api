import type { FieldResult, Layer, Level, Parameter, Source } from '../api/types'
import { reasonText } from '../i18n/reasons'

export const hasData = (l: Layer | undefined): l is Layer & Required<Pick<Layer, 'png_url' | 'geotiff_url' | 'stats' | 'colormap' | 'confidence'>> =>
  !!l && (l.status === 'ok' || l.status === 'partial') && !!l.png_url && !!l.stats && !!l.colormap && !!l.confidence

export const getLayer = (field: FieldResult | undefined, p: Parameter, s: Source) =>
  field?.layers.find((l) => l.parameter === p && l.source === s)

/** Sources worth offering for a parameter: everything except not_applicable (unavailable ones are shown greyed). */
export const sourcesFor = (field: FieldResult | undefined, p: Parameter) =>
  (field?.layers ?? []).filter((l) => l.parameter === p && l.status !== 'not_applicable')

/** Order in which a source is preferred when there is no `best` (most detailed first). */
const DETAIL_RANK: Source[] = ['best', 'lbeg_bodenschaetzung', 'lbeg_bk50', 'derived', 'soilgrids']

/**
 * Default source for a parameter (UI_BRIEF): `best` where it exists, otherwise the most detailed source with data.
 * Texture: the survey class where it covers any of the field, else SoilGrids clay %.
 */
export function pickDefaultSource(field: FieldResult | undefined, p: Parameter): Source | undefined {
  const withData = sourcesFor(field, p).filter(hasData)
  if (p === 'texture') {
    const survey = withData.find((l) => l.source === 'lbeg_bodenschaetzung' && (l.coverage ?? 0) > 0)
    if (survey) return survey.source
  }
  return DETAIL_RANK.find((s) => withData.some((l) => l.source === s)) ?? sourcesFor(field, p)[0]?.source
}

export interface StatusView {
  hidden: boolean
  disabled: boolean
  badge?: string
  explanation?: string
}

/** How a layer's status is presented: not_applicable hidden, unavailable greyed with reason, partial with coverage. */
export function statusView(l: Layer | undefined): StatusView {
  if (!l || l.status === 'not_applicable') return { hidden: true, disabled: true }
  if (l.status === 'unavailable') return { hidden: false, disabled: true, badge: 'Not available', explanation: reasonText(l.reason) }
  if (l.status === 'partial') {
    return { hidden: false, disabled: false, badge: `Covers ${Math.round((l.coverage ?? 0) * 100)} % of the field`, explanation: reasonText(l.reason) }
  }
  return { hidden: false, disabled: false }
}

export function fmt(v: number | null | undefined, digits?: number): string {
  if (v == null || !Number.isFinite(v)) return '–'
  const d = digits ?? (Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 0 : 1)
  return v.toLocaleString('en-GB', { maximumFractionDigits: d, minimumFractionDigits: d })
}

export const DIGITS: Record<Parameter, number> = { texture: 0, ph: 1, soc: 0, nfk: 0, bodenzahl: 0, yield_potential: 0 }

export function unitSuffix(unit: string | null | undefined) {
  if (!unit || unit === 'class' || unit.startsWith('index')) return ''
  if (unit === 'pH') return ''
  return unit === 'points' ? '' : ` ${unit}`
}

/** "likely 5.4–6.2 mm", or null for categorical layers. */
export function formatInterval(l: Layer): string | null {
  const iv = l.confidence?.interval_90
  if (!iv) return null
  const d = DIGITS[l.parameter]
  return `likely ${fmt(iv[0], d)}–${fmt(iv[1], d)}${unitSuffix(l.unit)}`
}

/** Main value of a layer in words: mean for continuous, dominant class for categorical. */
export function formatValue(l: Layer): string {
  const s = l.stats
  if (!s) return '–'
  if (l.colormap?.type === 'categorical') {
    const cls = l.colormap.classes.find((c) => c.code === s.dominant)
    return cls ? `${cls.code} (${cls.label ?? cls.code})` : (s.dominant ?? '–')
  }
  const v = l.parameter === 'texture' && s.usda_class ? `${fmt(s.mean, 0)} % clay (${s.usda_class})` : `${fmt(s.mean, DIGITS[l.parameter])}${unitSuffix(l.unit)}`
  return v
}

export const LEVEL_ORDER: Record<Level, number> = { low: 0, medium: 1, high: 2 }

/** Every pixel low → the map would be entirely grey under the masking rule. */
export const allLow = (l: Layer) => (l.confidence?.pixel_shares.low ?? 0) >= 0.999
