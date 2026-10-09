import path from 'node:path'
import { describe, expect, it } from 'vitest'
import { mockPostLayers } from '../api/client'
import { Proposed } from '../api/proposed'
import { FieldProps, FieldResult, LayersResponse, Meta, RunCurrent } from '../api/schema'
import type { FieldResult as FieldResultT, LayersRequest } from '../api/types'
import { DRIVERS } from '../i18n/drivers'
import { REASONS } from '../i18n/reasons'
import { mockDir, mockLayerFiles, proposedFiles, readJson, roundDeep, sampleRequest, sampleResponse } from './fixtures'

describe('API contract', () => {
  it('parses poc/samples/response.json', () => {
    expect(() => LayersResponse.parse(sampleResponse())).not.toThrow()
  })

  it('parses every mock fixture', () => {
    for (const f of mockLayerFiles()) FieldResult.parse(readJson(f))
    Meta.parse(readJson(path.join(mockDir, 'meta.json')))
    RunCurrent.parse(readJson(path.join(mockDir, 'runs_current.json')))
    const fc = readJson<{ features: { properties: unknown }[] }>(path.join(mockDir, 'fields.geojson'))
    expect(fc.features).toHaveLength(87)
    for (const f of fc.features) FieldProps.parse(f.properties)
    for (const f of proposedFiles()) Proposed.parse(readJson(f))
  })

  it('mock POST /soil/layers reproduces the sample response', async () => {
    const run = readJson<{ run_id: string; data_as_of: Record<string, string> }>(path.join(mockDir, 'runs_current.json'))
    const load = async (pid: string) => {
      try {
        return readJson<FieldResultT>(path.join(mockDir, 'layers', `${pid}.json`))
      } catch {
        return null
      }
    }
    const got = await mockPostLayers(sampleRequest() as LayersRequest, load, run)
    expect(roundDeep(got)).toEqual(roundDeep(sampleResponse()))
  })
})

describe('translations', () => {
  const all = mockLayerFiles().flatMap((f) => readJson<FieldResultT>(f).layers)

  it('every driver code in the data has farmer and audit text', () => {
    const codes = new Set(all.flatMap((l) => l.confidence?.drivers ?? []))
    expect([...codes].filter((c) => !(c in DRIVERS))).toEqual([])
  })

  it('every reason in the data has text', () => {
    const reasons = new Set(all.map((l) => l.reason).filter(Boolean) as string[])
    expect([...reasons].filter((r) => !(r in REASONS))).toEqual([])
  })
})
