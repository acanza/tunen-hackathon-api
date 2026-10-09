import type { Proposed } from './proposed'
import type { FieldCollection, FieldResult, LayersRequest, LayersResponse, Meta, Parameter, RunCurrent, Source } from './types'
import { PARAMETERS, SOURCES } from './schema'
import { localizeField } from '../i18n/soilClasses'

// The one place that knows where data comes from. VITE_API_URL unset → mocks in public/mock (exported from
// poc/store by scripts/export_fixtures.py). Set → the real API (proxied by Vite under the same paths).
export const USE_MOCK = !import.meta.env.VITE_API_URL

export interface SoilApi {
  getFields(): Promise<FieldCollection>
  getRun(): Promise<RunCurrent>
  postLayers(req: LayersRequest): Promise<LayersResponse>
  getMeta(): Promise<Meta>
  /** 🔴 proposed blocks (sampling plan, signals, crops, discrepancy, rank). null = not available for this field. */
  getProposed(plotId: string): Promise<Proposed | null>
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init)
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${url}: ${res.status} ${res.statusText}`)
  return res.json() as Promise<T>
}

const MOCK = `${import.meta.env.BASE_URL}mock`

/** Same rules as assemble_response() in poc/build_store.py, over the per-field fixtures. */
export async function mockPostLayers(
  req: LayersRequest,
  loadField: (plotId: string) => Promise<FieldResult | null>,
  run: RunCurrent,
): Promise<LayersResponse> {
  const params: readonly Parameter[] = req.parameters ?? PARAMETERS
  const sources: readonly Source[] = req.sources ?? SOURCES
  const fields = await Promise.all(
    req.features.map(async (feat): Promise<FieldResult> => {
      const pid = feat.properties?.plotId
      const known = pid ? await loadField(pid) : null
      const pick = (p: Parameter, s: Source) => known?.layers.find((l) => l.parameter === p && l.source === s)
      const layers = params.flatMap((p) =>
        sources.map((s) => {
          const l = pick(p, s)
          if (known && l) return l
          if (l?.status === 'not_applicable' || (!known && isNotApplicable(p, s))) {
            return { parameter: p, source: s, status: 'not_applicable' as const, reason: 'source_does_not_provide_parameter' }
          }
          return { parameter: p, source: s, status: 'unavailable' as const, reason: 'outside_coverage_area' }
        }),
      )
      return {
        id: feat.id ?? null,
        matched_plot_id: known?.matched_plot_id ?? null,
        match: known ? 'plot_id' : 'outside_coverage_area',
        field_name: known?.field_name ?? null,
        bounds: known?.bounds ?? null,
        layers,
      }
    }),
  )
  return { run_id: run.run_id, data_as_of: run.data_as_of, fields }
}

/** (source, parameter) pairs that exist at all; mirrors the source_parameters table. */
const PROVIDED = new Set([
  'soilgrids:texture', 'soilgrids:ph', 'soilgrids:soc', 'soilgrids:nfk', 'lbeg_bk50:nfk',
  'lbeg_bodenschaetzung:texture', 'lbeg_bodenschaetzung:bodenzahl',
  'derived:nfk', 'derived:bodenzahl', 'derived:yield_potential', 'best:nfk', 'best:bodenzahl',
])
export const isNotApplicable = (p: Parameter, s: Source) => !PROVIDED.has(`${s}:${p}`)

const fieldCache = new Map<string, Promise<FieldResult | null>>()
const loadMockField = (plotId: string) => {
  if (!fieldCache.has(plotId)) {
    fieldCache.set(plotId, fetch(`${MOCK}/layers/${encodeURIComponent(plotId)}.json`).then((r) => (r.ok ? r.json() : null)))
  }
  return fieldCache.get(plotId)!
}

const mockApi: SoilApi = {
  getFields: () => json(`${MOCK}/fields.geojson`),
  getRun: () => json(`${MOCK}/runs_current.json`),
  getMeta: () => json(`${MOCK}/meta.json`),
  postLayers: async (req) => mockPostLayers(req, loadMockField, await mockApi.getRun()),
  getProposed: async (plotId) => {
    const r = await fetch(`${MOCK}/proposed/${encodeURIComponent(plotId)}.json`)
    return r.ok && r.headers.get('content-type')?.includes('json') ? r.json() : null
  },
}

const httpApi: SoilApi = {
  getFields: () => json('/soil/fields'),
  getRun: () => json('/soil/runs/current'),
  postLayers: (req) => json('/soil/layers', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(req) }),
  // Not in the API contract yet (see plan: proposed GET /soil/meta). Falls back to the mock until it exists.
  getMeta: () => json<Meta>('/soil/meta').catch(() => mockApi.getMeta()),
  // 🔴 data-side work; mock until the endpoints exist.
  getProposed: (plotId) => mockApi.getProposed(plotId),
}

const baseApi: SoilApi = USE_MOCK ? mockApi : httpApi

/** English display labels for German soil classes, applied once for both mock and real API. */
export const api: SoilApi = {
  ...baseApi,
  postLayers: async (req) => {
    const res = await baseApi.postLayers(req)
    return { ...res, fields: res.fields.map(localizeField) }
  },
}

/** Request every layer of the given known fields. */
export const layersRequestFor = (plotIds: string[], parameters?: Parameter[], sources?: Source[]): LayersRequest => ({
  type: 'FeatureCollection',
  features: plotIds.map((plotId) => ({ type: 'Feature', id: plotId, properties: { plotId }, geometry: null })),
  ...(parameters && { parameters }),
  ...(sources && { sources }),
})
