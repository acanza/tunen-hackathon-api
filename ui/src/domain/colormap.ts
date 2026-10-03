import type { Colormap } from '../api/types'

export type RGBA = [number, number, number, number]

export const hexRgb = (h: string): [number, number, number] => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number]

/** Colour of one value, identical to colorize() in poc/build_store.py (linear between stops, clipped). null = no data. */
export function colorAt(cmap: Colormap, v: number): RGBA | null {
  if (!Number.isFinite(v)) return null
  if (cmap.type === 'categorical') {
    const c = cmap.classes.find((k) => k.value === v)
    return c ? [...hexRgb(c.color), 255] : null
  }
  const s = cmap.stops
  const x = Math.min(Math.max(v, s[0][0]), s[s.length - 1][0])
  let i = 0
  while (i < s.length - 2 && x > s[i + 1][0]) i++
  const [x0, c0] = s[i]
  const [x1, c1] = s[i + 1] ?? s[i]
  const t = x1 === x0 ? 0 : (x - x0) / (x1 - x0)
  const a = hexRgb(c0)
  const b = hexRgb(c1)
  return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * t)).concat(255) as RGBA
}

export const rgbaCss = ([r, g, b, a]: RGBA) => `rgba(${r},${g},${b},${a / 255})`

/** CSS gradient for a continuous legend bar. */
export function gradientCss(cmap: Colormap): string {
  if (cmap.type === 'categorical') return ''
  const s = cmap.stops
  const lo = s[0][0]
  const span = s[s.length - 1][0] - lo || 1
  return `linear-gradient(to right, ${s.map(([x, c]) => `${c} ${(((x - lo) / span) * 100).toFixed(1)}%`).join(', ')})`
}

/** Friendlier labels for the source-mask legend. */
export function sourceLegend(cm: Colormap): Colormap {
  if (cm.type !== 'categorical') return cm
  const label: Record<string, string> = { lbeg_bodenschaetzung: 'Official survey', derived: 'Our model', soilgrids: 'SoilGrids' }
  return { ...cm, classes: cm.classes.map((c) => ({ ...c, label: label[c.code] ?? c.label, code: '' })) }
}
