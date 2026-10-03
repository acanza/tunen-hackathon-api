// Yield view maths (UI_BRIEF feature 0). Pure client-side: the farmer supplies the level, we supply the pattern.

export interface YieldZone {
  label: string
  from: number
  to: number
  share: number
  meanIndex: number
  tPerHa: number
}

/** Expected t/ha for one index value: farmer's usual yield × index / 100. */
export const expectedYield = (usualTPerHa: number, index: number) => (usualTPerHa * index) / 100

export const ZONE_EDGES = [-Infinity, 97, 103, Infinity]
const ZONE_LABELS = ['Weaker (below 97)', 'Average (97–103)', 'Stronger (above 103)']

/** Group per-pixel index values (band 1 of the yield GeoTIFF) into weaker / average / stronger zones. */
export function yieldZones(values: ArrayLike<number>, usualTPerHa: number, edges = ZONE_EDGES): YieldZone[] {
  const sums = new Array(edges.length - 1).fill(0)
  const counts = new Array(edges.length - 1).fill(0)
  let n = 0
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (!Number.isFinite(v)) continue
    const z = edges.findIndex((e, k) => k < edges.length - 1 && v >= e && v < edges[k + 1])
    sums[z] += v
    counts[z]++
    n++
  }
  return counts.map((c, k) => {
    const meanIndex = c ? sums[k] / c : NaN
    return {
      label: ZONE_LABELS[k] ?? `${edges[k]}–${edges[k + 1]}`,
      from: edges[k],
      to: edges[k + 1],
      share: n ? c / n : 0,
      meanIndex,
      tPerHa: c ? expectedYield(usualTPerHa, meanIndex) : NaN,
    }
  })
}

/** Field total in tonnes: mean index × usual yield × area. */
export const fieldTotal = (usualTPerHa: number, meanIndex: number, areaHa: number) => expectedYield(usualTPerHa, meanIndex) * areaHa

/** "10 % of the field is at least 3 % below its average" from p10/p90. */
export function spreadSentences(p10?: number, p90?: number): string[] {
  const out: string[] = []
  if (p10 != null) {
    const d = Math.round(100 - p10)
    out.push(d >= 1 ? `10 % of the field is at least ${d} % below its average.` : '10 % of the field is within 1 % of its average at the weak end.')
  }
  if (p90 != null) {
    const d = Math.round(p90 - 100)
    out.push(d >= 1 ? `10 % of the field is at least ${d} % above its average.` : 'The strongest 10 % is within 1 % of the average.')
  }
  return out
}
