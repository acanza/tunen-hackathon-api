import { describe, expect, it } from 'vitest'
import type { FieldResult } from '../api/types'
import { farmerSentences } from '../domain/sentences'
import { lowStripe, maskPixel } from '../map/masking'
import { CONF } from '../map/raster'
import { sampleResponse } from './fixtures'

const px = (r: number, g: number, b: number, a = 255) => new Uint8ClampedArray([r, g, b, a])

describe('masking rule', () => {
  it('high keeps the layer colour', () => {
    const p = px(10, 200, 30)
    maskPixel(p, 0, CONF.HIGH, 0, 1)
    expect([...p]).toEqual([10, 200, 30, 255])
  })
  it('low never shows the layer colour', () => {
    for (const [r, c] of [[0, 0], [0, 4]]) {
      const p = px(10, 200, 30)
      maskPixel(p, 0, CONF.LOW, r, c)
      expect(p[0]).toBe(p[1]) // grey: r = g = b
      expect(p[1]).toBe(p[2])
      expect(p[3]).toBe(255)
      expect(lowStripe(r, c) ? p[0] < 128 : p[0] > 128).toBe(true)
    }
  })
  it('a coloured pixel with no confidence value is treated as low', () => {
    const p = px(10, 200, 30)
    maskPixel(p, 0, NaN, 0, 3)
    expect(p[0]).toBe(p[1])
  })
  it('transparent stays transparent', () => {
    const p = px(0, 0, 0, 0)
    maskPixel(p, 0, CONF.LOW, 0, 0)
    expect(p[3]).toBe(0)
  })
})

describe('farmer sentences', () => {
  const [west, east] = (sampleResponse() as { fields: FieldResult[] }).fields
  it('every sentence references a layer that exists with data', () => {
    for (const f of [west, east]) {
      for (const s of farmerSentences(f, null)) {
        for (const r of s.refs) {
          const l = f.layers.find((x) => x.parameter === r.parameter && x.source === r.source)
          expect(l?.status === 'ok' || l?.status === 'partial').toBe(true)
        }
      }
    }
  })
  it('low-confidence pH leads to "can’t tell" rather than a value', () => {
    const ph = farmerSentences(west, null).find((s) => s.topic === 'pH / lime')!
    expect(ph.text).toMatch(/can’t tell/)
  })
  it('official Bodenzahl is stated as a value with its source', () => {
    expect(farmerSentences(west, null)[0].text).toMatch(/soil score about \d+ out of 100 \(official survey\)/)
  })
})
