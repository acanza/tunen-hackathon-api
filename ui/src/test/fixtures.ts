import { readdirSync, readFileSync } from 'node:fs'
import path from 'node:path'

export const UI = path.resolve(import.meta.dirname, '../..')
export const REPO = path.resolve(UI, '..')
export const readJson = <T = unknown>(p: string): T => JSON.parse(readFileSync(p, 'utf8'))

export const sampleRequest = () => readJson(path.join(REPO, 'poc/samples/request.json'))
export const sampleResponse = () => readJson(path.join(REPO, 'poc/samples/response.json'))
export const mockDir = path.join(UI, 'public/mock')
export const mockLayerFiles = () => readdirSync(path.join(mockDir, 'layers')).map((f) => path.join(mockDir, 'layers', f))
export const proposedFiles = () => {
  try {
    return readdirSync(path.join(mockDir, 'proposed')).map((f) => path.join(mockDir, 'proposed', f))
  } catch {
    return []
  }
}

/** Round floats so JSON comparisons ignore float noise. */
export function roundDeep(v: unknown, digits = 6): unknown {
  if (typeof v === 'number') return Number(v.toFixed(digits))
  if (Array.isArray(v)) return v.map((x) => roundDeep(x, digits))
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, roundDeep(x, digits)]))
  return v
}
