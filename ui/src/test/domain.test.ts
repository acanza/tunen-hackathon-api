import { describe, expect, it } from 'vitest'
import type { Colormap, FieldResult } from '../api/types'
import { colorAt } from '../domain/colormap'
import { samplingCsv, samplingGpx } from '../domain/export'
import { formatInterval, pickDefaultSource, statusView } from '../domain/layers'
import { expectedYield, spreadSentences, yieldZones } from '../domain/yield'
import { sampleResponse } from './fixtures'

const [west, east, sliver] = (sampleResponse() as { fields: FieldResult[] }).fields

describe('pickDefaultSource', () => {
  it('prefers best where it exists', () => {
    expect(pickDefaultSource(west, 'bodenzahl')).toBe('best')
    expect(pickDefaultSource(east, 'nfk')).toBe('best')
  })
  it('texture: survey class on both sides of the border (LBEG west, LAGB east)', () => {
    expect(pickDefaultSource(west, 'texture')).toBe('lbeg_bodenschaetzung')
    expect(pickDefaultSource(east, 'texture')).toBe('lbeg_bodenschaetzung')
  })
  it('single-source parameters', () => {
    expect(pickDefaultSource(west, 'ph')).toBe('soilgrids')
    expect(pickDefaultSource(sliver, 'yield_potential')).toBe('derived')
  })
})

describe('statusView', () => {
  it('hides not_applicable, explains unavailable', () => {
    const na = east.layers.find((l) => l.status === 'not_applicable')
    expect(statusView(na).hidden).toBe(true)
    const un = east.layers.find((l) => l.parameter === 'nfk' && l.source === 'lbeg_bk50') // BK50 is Lower Saxony only
    expect(statusView(un)).toMatchObject({ disabled: true, explanation: expect.stringContaining('Lower Saxony') })
  })
  it('formats intervals', () => {
    const ph = west.layers.find((l) => l.parameter === 'ph')!
    expect(formatInterval(ph)).toMatch(/^likely \d\.\d–\d\.\d$/)
  })
})

describe('colorAt', () => {
  const cont: Colormap = { type: 'continuous', stops: [[0, '#000000'], [10, '#ffffff']] }
  it('interpolates and clips like build_store.colorize', () => {
    expect(colorAt(cont, 5)).toEqual([128, 128, 128, 255])
    expect(colorAt(cont, -3)).toEqual([0, 0, 0, 255])
    expect(colorAt(cont, 99)).toEqual([255, 255, 255, 255])
    expect(colorAt(cont, NaN)).toBeNull()
  })
  it('maps categorical values', () => {
    const cat: Colormap = { type: 'categorical', classes: [{ value: 2, code: 'Sl', color: '#ff0000' }] }
    expect(colorAt(cat, 2)).toEqual([255, 0, 0, 255])
    expect(colorAt(cat, 3)).toBeNull()
  })
})

describe('yield', () => {
  it('scales the farmer’s usual yield by the index', () => {
    expect(expectedYield(7.5, 100)).toBe(7.5)
    expect(expectedYield(7.5, 90)).toBeCloseTo(6.75)
  })
  it('groups pixels into zones, ignoring NaN', () => {
    const z = yieldZones([95, 96, 100, 104, NaN], 8)
    expect(z.map((x) => x.share)).toEqual([0.5, 0.25, 0.25])
    expect(z[0].tPerHa).toBeCloseTo(8 * 0.955)
  })
  it('writes spread sentences from p10/p90', () => {
    expect(spreadSentences(97, 102)).toEqual(['10 % of the field is at least 3 % below its average.', '10 % of the field is at least 2 % above its average.'])
  })
})

describe('sampling export', () => {
  const pts = [{ rank: 1, lat: 52.35, lon: 11.09, decision: 'liming', parameter: 'ph', decision_uncertainty: 0.94, current_estimate: 5.6, interval_90: [4.9, 6.4] as [number, number], why: 'pH at the threshold, "coin flip"' }]
  it('GPX has one escaped waypoint', () => {
    const g = samplingGpx('Heuweg', pts)
    expect(g).toContain('<wpt lat="52.35" lon="11.09">')
    expect(g).toContain('&quot;coin flip&quot;')
  })
  it('CSV quotes cells with commas/quotes', () => {
    const lines = samplingCsv('Heuweg', pts).trim().split('\n')
    expect(lines).toHaveLength(2)
    expect(lines[1]).toContain('"pH at the threshold, ""coin flip"""')
  })
})
