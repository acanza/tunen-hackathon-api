import type { SamplingPoint } from '../api/proposed'

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

/** GPX 1.1 waypoints for a phone/GPS. */
export function samplingGpx(fieldName: string, points: SamplingPoint[]): string {
  const wpts = points
    .map(
      (p) =>
        `  <wpt lat="${p.lat}" lon="${p.lon}">\n    <name>${esc(`${fieldName} #${p.rank}`)}</name>\n    <desc>${esc(p.why)}</desc>\n  </wpt>`,
    )
    .join('\n')
  return `<?xml version="1.0" encoding="UTF-8"?>\n<gpx version="1.1" creator="Seggerde soil POC" xmlns="http://www.topografix.com/GPX/1/1">\n${wpts}\n</gpx>\n`
}

const csvCell = (v: unknown) => {
  const s = String(v ?? '')
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function samplingCsv(fieldName: string, points: SamplingPoint[]): string {
  const head = ['field', 'rank', 'lat', 'lon', 'decision', 'parameter', 'current_estimate', 'lo90', 'hi90', 'decision_uncertainty', 'why']
  const rows = points.map((p) => [fieldName, p.rank, p.lat, p.lon, p.decision, p.parameter, p.current_estimate, p.interval_90[0], p.interval_90[1], p.decision_uncertainty, p.why])
  return [head, ...rows].map((r) => r.map(csvCell).join(',')).join('\n') + '\n'
}

export function download(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = Object.assign(document.createElement('a'), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}
