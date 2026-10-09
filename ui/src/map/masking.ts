import type { Bounds } from '../api/types'
import { CONF, type Raster } from './raster'

// The masking rule (UI_BRIEF): high → layer colour; medium → colour + light hatch; low → grey + hatch, no
// layer colour; no data → transparent. Built client-side until the data side ships `masked_png_url`:
// take the server's layer PNG (EPSG:3857, aligned to `bounds`) and, for each PNG pixel, look up the
// confidence (band 4) of the GeoTIFF at that pixel's centre.

const GREY: [number, number, number] = [189, 189, 189]
const DARK: [number, number, number] = [80, 80, 80]
const LIGHT: [number, number, number] = [255, 255, 255]

/** Stripe patterns in image pixels (2.5 m each): dark every 8 px for low, faint every 10 px for medium. */
export const lowStripe = (r: number, c: number) => (r + c) % 8 < 2
export const mediumStripe = (r: number, c: number) => (r + c) % 10 < 1

/** Recolour one pixel in place given its confidence class. Exported for tests. */
export function maskPixel(px: Uint8ClampedArray, i: number, conf: number, r: number, c: number) {
  if (px[i + 3] === 0) return // no data: the PNG is already transparent here
  // A coloured PNG pixel whose centre misses the GeoTIFF (edge resampling) is treated as low: never leak colour.
  if (!Number.isFinite(conf) || conf === CONF.LOW) {
    const [R, G, B] = lowStripe(r, c) ? DARK : GREY
    px[i] = R
    px[i + 1] = G
    px[i + 2] = B
    px[i + 3] = 255
  } else if (conf === CONF.MEDIUM && mediumStripe(r, c)) {
    for (let k = 0; k < 3; k++) px[i + k] = Math.round(px[i + k] * 0.45 + LIGHT[k] * 0.55)
  }
}

const mercY = (lat: number) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360))
const invMercY = (y: number) => (Math.atan(Math.exp(y)) * 360) / Math.PI - 90

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error(`image ${url}`))
    img.src = url
  })
}

const cache = new Map<string, Promise<string>>()

/** Masked overlay as a data URL with the same bounds as `pngUrl`. */
export function maskedPng(pngUrl: string, bounds: Bounds, raster: Raster): Promise<string> {
  if (!cache.has(pngUrl)) cache.set(pngUrl, render(pngUrl, bounds, raster))
  return cache.get(pngUrl)!
}

async function render(pngUrl: string, bounds: Bounds, raster: Raster): Promise<string> {
  const img = await loadImage(pngUrl)
  const { width: w, height: h } = img
  const canvas = Object.assign(document.createElement('canvas'), { width: w, height: h })
  const ctx = canvas.getContext('2d')!
  ctx.drawImage(img, 0, 0)
  const data = ctx.getImageData(0, 0, w, h)
  const [[s, west], [n, east]] = bounds
  const yTop = mercY(n)
  const yBot = mercY(s)
  for (let r = 0; r < h; r++) {
    const lat = invMercY(yTop - ((r + 0.5) / h) * (yTop - yBot))
    for (let c = 0; c < w; c++) {
      const i = (r * w + c) * 4
      if (data.data[i + 3] === 0) continue
      const lon = west + ((c + 0.5) / w) * (east - west)
      const v = raster.sample(lat, lon)
      maskPixel(data.data, i, v ? v[3] : NaN, r, c)
    }
  }
  ctx.putImageData(data, 0, 0)
  return canvas.toDataURL('image/png')
}
