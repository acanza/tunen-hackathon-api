import type { Proposed } from '../api/proposed'
import type { FieldResult, Layer, Parameter, Source } from '../api/types'
import { DIGITS, fmt, getLayer, hasData, pickDefaultSource } from './layers'

// Farmer-view sentences, templated in the UI until the data side produces them (UI_BRIEF feature 5).
// Every sentence lists the audit rows its numbers come from, so the farmer view stays 1:1 traceable.

export interface Sentence {
  topic: string
  text: string
  refs: Array<{ parameter: Parameter; source: Source }>
}

export const auditId = (p: string, s: string) => `audit-${p}-${s}`

const origin = (l: Layer) => {
  const shares = l.stats?.source_shares
  if (shares) {
    const off = shares.lbeg_bodenschaetzung ?? 0
    if (off >= 0.95) return 'official survey'
    if (off > 0) return `${Math.round(off * 100)} % official survey, rest our model`
    return 'estimated by our model'
  }
  return { soilgrids: 'coarse global map', lbeg_bodenschaetzung: 'official survey', lbeg_bk50: 'state soil map', derived: 'estimated by our model', best: 'best available' }[l.source]
}

const ref = (l: Layer) => ({ parameter: l.parameter, source: l.source })
const layerFor = (f: FieldResult, p: Parameter) => {
  const s = pickDefaultSource(f, p)
  const l = s ? getLayer(f, p, s) : undefined
  return hasData(l) ? l : undefined
}
const range = (l: Layer, unit = '') => {
  const iv = l.confidence?.interval_90
  return iv ? `${fmt(iv[0], DIGITS[l.parameter])}–${fmt(iv[1], DIGITS[l.parameter])}${unit}` : ''
}

export function farmerSentences(f: FieldResult, proposed: Proposed | null): Sentence[] {
  const out: Sentence[] = []

  const bz = layerFor(f, 'bodenzahl')
  if (bz?.stats?.mean != null) {
    const m = bz.stats.mean
    // Bodenzahl (soil score) runs 0–100; this farm spans 17–49. ≤ 35 reads as poor (typically sandy), ≤ 55 moderate.
    const quality = m <= 35 ? 'poor, typically sandy' : m <= 55 ? 'moderate' : 'good'
    out.push(
      bz.confidence?.level === 'low'
        ? { topic: 'Soil quality', text: `Soil quality is uncertain here: soil score likely ${range(bz)} out of 100 (${origin(bz)}).`, refs: [ref(bz)] }
        : { topic: 'Soil quality', text: `This field has ${quality} soil: soil score about ${Math.round(m)} out of 100 (${origin(bz)}).`, refs: [ref(bz)] },
    )
  }

  const tx = layerFor(f, 'texture')
  if (tx?.stats) {
    if (tx.colormap?.type === 'categorical') {
      const cls = tx.colormap.classes.find((c) => c.code === tx.stats!.dominant)
      out.push({ topic: 'Soil type', text: `Mostly ${(cls?.label ?? tx.stats.dominant ?? '').toLowerCase()}, according to the official soil survey.`, refs: [ref(tx)] })
    } else if (tx.stats.usda_class) {
      out.push({ topic: 'Soil type', text: `Probably ${tx.stats.usda_class}, from a coarse global map; the exact soil type is uncertain.`, refs: [ref(tx)] })
    }
  }

  const nfk = layerFor(f, 'nfk')
  if (nfk?.stats?.mean != null) {
    const m = nfk.stats.mean
    out.push(
      nfk.confidence?.level === 'low'
        ? { topic: 'Water', text: `We can’t pin down how much water the soil holds for plants: likely ${range(nfk, ' mm')}${m < 90 ? ', on the low side' : ''}. Dry springs matter on this farm.`, refs: [ref(nfk)] }
        : { topic: 'Water', text: `The soil holds about ${Math.round(m)} mm of water plants can use, which is ${m < 90 ? 'low, so dry springs hit it hard' : m < 140 ? 'moderate' : 'good'}.`, refs: [ref(nfk)] },
    )
  }

  const ph = layerFor(f, 'ph')
  const firstPh = proposed?.sampling_plan?.points.find((p) => p.parameter === 'ph')
  if (ph?.stats?.mean != null) {
    out.push(
      ph.confidence?.level === 'low'
        ? {
            topic: 'pH / lime',
            text: `We can’t tell from public data whether this field needs lime (pH likely ${range(ph)}).${firstPh ? ` One soil sample at point ${firstPh.rank} would settle it.` : ' A soil sample would settle it.'}`,
            refs: [ref(ph)],
          }
        : { topic: 'pH / lime', text: `Topsoil pH is about ${fmt(ph.stats.mean, 1)}.`, refs: [ref(ph)] },
    )
  }

  const y = getLayer(f, 'yield_potential', 'derived')
  if (hasData(y) && y.stats.p10 != null && y.stats.p90 != null) {
    const spread = Math.round(y.stats.p90 - y.stats.p10)
    out.push(
      y.confidence.level === 'low'
        ? { topic: 'Yield pattern', text: 'We have no reliable satellite history for this field, so we can’t show where it yields more or less.', refs: [ref(y)] }
        : {
            topic: 'Yield pattern',
            text: spread <= 3 ? 'The field yields fairly evenly: its stronger and weaker parts differ by only a few percent.' : `Parts of the field consistently yield about ${spread} % more than others.`,
            refs: [ref(y)],
          },
    )
  }
  return out
}
