import type { ReactNode } from 'react'
import type { Level } from '../api/types'
import { LEVEL_LABEL } from '../i18n/labels'

const LEVEL_STYLE: Record<Level, string> = {
  high: 'bg-emerald-100 text-emerald-900 ring-emerald-700/30',
  medium: 'bg-amber-100 text-amber-900 ring-amber-700/30',
  low: 'bg-stone-100 text-stone-800 ring-stone-500/40',
}
/** Swatch matching how the map draws that confidence. */
const LEVEL_SWATCH: Record<Level, string> = { high: 'bg-emerald-600', medium: 'bg-hatch-medium', low: 'bg-hatch' }

/** Colour + icon + word: never colour alone. */
export function ConfidenceBadge({ level, compact = false }: { level: Level; compact?: boolean }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${LEVEL_STYLE[level]}`}>
      <span aria-hidden className={`h-2.5 w-2.5 rounded-sm ring-1 ring-black/15 ${LEVEL_SWATCH[level]}`} />
      {compact ? level[0].toUpperCase() + level.slice(1) : LEVEL_LABEL[level]}
    </span>
  )
}

export function Chip({ children, tone = 'neutral', title }: { children: ReactNode; tone?: 'neutral' | 'warn' | 'info' | 'good' | 'bad'; title?: string }) {
  const style = {
    neutral: 'bg-stone-100 text-stone-700 ring-stone-400/40',
    warn: 'bg-amber-50 text-amber-900 ring-amber-600/40',
    info: 'bg-sky-50 text-sky-900 ring-sky-600/30',
    good: 'bg-emerald-50 text-emerald-900 ring-emerald-600/30',
    bad: 'bg-rose-50 text-rose-900 ring-rose-600/30',
  }[tone]
  return (
    <span title={title} className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}>
      {children}
    </span>
  )
}

/** Marks every panel built on proposed (not yet produced) data. */
export function PreviewBadge() {
  return (
    <Chip tone="info" title="Built on the proposed data shape with mock values. The data side doesn’t produce this yet.">
      Preview: mock data
    </Chip>
  )
}

export function Panel({ title, children, actions, className = '' }: { title?: ReactNode; children: ReactNode; actions?: ReactNode; className?: string }) {
  return (
    <section className={`rounded-lg border border-stone-200 bg-white p-4 shadow-sm ${className}`}>
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold text-stone-900">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}

export function Loading({ what = 'Loading' }: { what?: string }) {
  return <p className="p-4 text-sm text-stone-500">{what}…</p>
}

export function ErrorNote({ error }: { error: unknown }) {
  return <p className="rounded-md bg-rose-50 p-3 text-sm text-rose-900">Couldn’t load data: {String((error as Error)?.message ?? error)}</p>
}
