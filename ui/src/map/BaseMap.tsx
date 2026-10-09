import type { LatLngBoundsExpression } from 'leaflet'
import { useEffect, type ReactNode } from 'react'
import { LayersControl, MapContainer, TileLayer, useMap } from 'react-leaflet'

function FitBounds({ bounds }: { bounds?: LatLngBoundsExpression }) {
  const map = useMap()
  const key = JSON.stringify(bounds)
  useEffect(() => {
    if (bounds) map.fitBounds(bounds, { padding: [24, 24] })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key])
  return null
}

const SEGGERDE: [number, number] = [52.36, 11.07]

export function BaseMap({ bounds, children, className = 'h-full w-full', aerial = false }: {
  bounds?: LatLngBoundsExpression
  children?: ReactNode
  className?: string
  aerial?: boolean
}) {
  return (
    <MapContainer center={SEGGERDE} zoom={13} className={className}>
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked={!aerial} name="Map">
          <TileLayer
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            maxZoom={19}
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer checked={aerial} name="Aerial">
          <TileLayer
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
            attribution="Imagery &copy; Esri"
            maxZoom={19}
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      <FitBounds bounds={bounds} />
      {children}
    </MapContainer>
  )
}
