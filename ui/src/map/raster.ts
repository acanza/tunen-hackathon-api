import { fromArrayBuffer } from 'geotiff'
import proj4 from 'proj4'

// Per-pixel access to the layer GeoTIFFs (EPSG:32632, 10 m): band 1 value, 2 lo90, 3 hi90, 4 confidence
// (1 low, 2 medium, 3 high), 5 source code (best only). Nodata is NaN. Files are per field and tiny.

proj4.defs('EPSG:32632', '+proj=utm +zone=32 +datum=WGS84 +units=m +no_defs')
const toUtm = proj4('EPSG:4326', 'EPSG:32632')

export const CONF = { LOW: 1, MEDIUM: 2, HIGH: 3 } as const

export interface Raster {
  width: number
  height: number
  bands: Float32Array[]
  /** Band values at a lat/lon (nearest pixel), or null outside the raster / on nodata. */
  sample(lat: number, lon: number): number[] | null
  /** Finite values of one band (1-based). */
  values(band: number): number[]
}

const cache = new Map<string, Promise<Raster>>()

export function loadRaster(url: string): Promise<Raster> {
  const clean = url.split('#')[0]
  if (!cache.has(clean)) cache.set(clean, fetchRaster(clean))
  return cache.get(clean)!
}

async function fetchRaster(url: string): Promise<Raster> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`GET ${url}: ${res.status}`)
  const tiff = await fromArrayBuffer(await res.arrayBuffer())
  const img = await tiff.getImage()
  const [ox, oy] = img.getOrigin()
  const [rx, ry] = img.getResolution()
  const width = img.getWidth()
  const height = img.getHeight()
  const raw = (await img.readRasters()) as unknown as ArrayLike<number>[]
  const bands = Array.from(raw, (b) => Float32Array.from(b))
  return {
    width,
    height,
    bands,
    sample(lat, lon) {
      const [x, y] = toUtm.forward([lon, lat])
      const col = Math.floor((x - ox) / rx)
      const row = Math.floor((y - oy) / ry)
      if (col < 0 || row < 0 || col >= width || row >= height) return null
      const v = bands.map((b) => b[row * width + col])
      return Number.isFinite(v[0]) ? v : null
    },
    values(band) {
      return Array.from(bands[band - 1]).filter(Number.isFinite)
    },
  }
}
