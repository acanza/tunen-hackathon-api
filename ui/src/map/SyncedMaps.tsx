import type { Map as LMap } from 'leaflet'
import { useEffect, useState } from 'react'
import { useMap } from 'react-leaflet'

interface SyncGroup {
  maps: Set<LMap>
  busy: boolean
}

/** Keeps several Leaflet maps on the same centre/zoom. Put <SyncMember group={g} /> inside each map. */
export function useSyncGroup(): SyncGroup {
  return useState<SyncGroup>(() => ({ maps: new Set(), busy: false }))[0]
}

export function SyncMember({ group }: { group: SyncGroup }) {
  const map = useMap()
  useEffect(() => {
    group.maps.add(map)
    const onMove = () => {
      if (group.busy) return // this move was caused by another member
      group.busy = true
      for (const other of group.maps) if (other !== map) other.setView(map.getCenter(), map.getZoom(), { animate: false })
      group.busy = false
    }
    map.on('move', onMove)
    return () => {
      map.off('move', onMove)
      group.maps.delete(map)
    }
  }, [map, group])
  return null
}
