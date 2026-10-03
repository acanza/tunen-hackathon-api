import { useQuery } from '@tanstack/react-query'
import { api, layersRequestFor } from './client'

// The store is frozen per run, so cached data never goes stale within a session.
const forever = { staleTime: Infinity, gcTime: Infinity } as const

export const useFields = () => useQuery({ queryKey: ['fields'], queryFn: api.getFields, ...forever })
export const useRun = () => useQuery({ queryKey: ['run'], queryFn: api.getRun, ...forever })
export const useMeta = () => useQuery({ queryKey: ['meta'], queryFn: api.getMeta, ...forever })
export const useProposed = (plotId: string | undefined) =>
  useQuery({ queryKey: ['proposed', plotId], queryFn: () => api.getProposed(plotId!), enabled: !!plotId, ...forever })

/** All layers of one field. */
export const useField = (plotId: string | undefined) =>
  useQuery({
    queryKey: ['field', plotId],
    queryFn: async () => (await api.postLayers(layersRequestFor([plotId!]))).fields[0],
    enabled: !!plotId,
    ...forever,
  })

/** All layers of many fields in one request (≤ 200 features per the contract). Used by the overview. */
export const useFarmLayers = (plotIds: string[] | undefined) =>
  useQuery({
    queryKey: ['farm-layers', plotIds?.length],
    queryFn: () => api.postLayers(layersRequestFor(plotIds!)),
    enabled: !!plotIds?.length,
    ...forever,
  })
