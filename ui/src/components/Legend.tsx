import type { Colormap } from '../api/types'
import { gradientCss } from '../domain/colormap'

export function Legend({ colormap, title, onlyCodes, masking = true }: { colormap: Colormap; title?: string; onlyCodes?: string[]; masking?: boolean }) {
  return (
    <div className="space-y-1.5 text-xs text-stone-700">
      {title && <div className="font-medium">{title}</div>}
      {colormap.type === 'categorical' ? (
        <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
          {colormap.classes
            .filter((c) => !onlyCodes || onlyCodes.includes(c.code))
            .map((c) => (
              <li key={c.value} className="flex items-center gap-1.5">
                <span className="h-3 w-3 shrink-0 rounded-sm ring-1 ring-black/10" style={{ background: c.color }} />
                <span>
                  {c.code && <b>{c.code} </b>}
                  {c.label && c.label !== c.code && c.label}
                </span>
              </li>
            ))}
        </ul>
      ) : (
        <div>
          <div className="h-3 rounded-sm ring-1 ring-black/10" style={{ background: gradientCss(colormap) }} />
          <div className="relative mt-0.5 h-4">
            {colormap.stops.map(([x], i) => {
              const lo = colormap.stops[0][0]
              const span = colormap.stops[colormap.stops.length - 1][0] - lo || 1
              return (
                <span key={i} className="absolute -translate-x-1/2 tabular-nums" style={{ left: `${((x - lo) / span) * 100}%` }}>
                  {x}
                </span>
              )
            })}
          </div>
          {colormap.unit && <div className="text-stone-500">{colormap.unit}</div>}
        </div>
      )}
      {masking && <MaskingKey />}
    </div>
  )
}

/** Key for the masking rule, shown under every legend. */
export function MaskingKey() {
  return (
    <ul className="flex flex-wrap gap-x-3 gap-y-1 pt-1 text-stone-600">
      <li className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-hatch-medium ring-1 ring-black/10" /> medium confidence
      </li>
      <li className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-sm bg-hatch ring-1 ring-black/10" /> uncertain: range only
      </li>
    </ul>
  )
}
