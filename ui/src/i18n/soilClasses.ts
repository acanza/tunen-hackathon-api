import type { FieldResult, Layer } from '../api/types'

// English names for the German soil survey classes (Bodenart codes). The data keeps the German labels; the app
// translates at the API boundary (`localizeField`) so every legend, tooltip and sentence is in English.
export const SOIL_CLASS_EN: Record<string, string> = {
  S: 'Sand',
  Sl: 'Slightly loamy sand',
  lS: 'Loamy sand',
  SL: 'Strongly loamy sand',
  sL: 'Sandy loam',
  L: 'Loam',
  LT: 'Heavy loam',
  T: 'Clay',
  Mo: 'Peat',
}

function localizeLayer(l: Layer): Layer {
  if (l.colormap?.type !== 'categorical' || l.parameter !== 'texture') return l
  return { ...l, colormap: { ...l.colormap, classes: l.colormap.classes.map((c) => ({ ...c, label: SOIL_CLASS_EN[c.code] ?? c.label })) } }
}

export const localizeField = (f: FieldResult): FieldResult => ({ ...f, layers: f.layers.map(localizeLayer) })
