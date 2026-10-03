import type { Level, Parameter, Source, Stats } from '../api/types'

export const PARAM_LABEL: Record<Parameter, string> = {
  texture: 'Soil texture',
  ph: 'pH',
  soc: 'Organic carbon',
  nfk: 'Plant-available water',
  bodenzahl: 'Soil quality score',
  yield_potential: 'Yield potential',
}

/** What depth/meaning each value refers to (UI_BRIEF §1: label nFK and Bodenzahl with their real meaning). */
export const PARAM_DEPTH: Record<Parameter, string> = {
  texture: 'topsoil 0–30 cm (survey: soil class)',
  ph: 'topsoil 0–30 cm',
  soc: 'topsoil 0–30 cm',
  nfk: 'water plants can use in the root zone (~60–110 cm); German: nFK',
  bodenzahl: 'official German 0–100 soil score for the whole profile (Bodenzahl)',
  yield_potential: '100 = this field’s own average',
}

export const SOURCE_LABEL: Record<Source, string> = {
  soilgrids: 'SoilGrids (global)',
  lbeg_bk50: 'LBEG BK50',
  lbeg_bodenschaetzung: 'Official survey',
  derived: 'Our model',
  best: 'Best available',
}

export const SOURCE_COLOR: Record<string, string> = {
  lbeg_bodenschaetzung: '#1b7837',
  lbeg_bk50: '#5aae61',
  derived: '#9970ab',
  soilgrids: '#e08214',
}

export const LEVEL_LABEL: Record<Level, string> = { high: 'High confidence', medium: 'Medium confidence', low: 'Low confidence' }

export const ZONE_TEXT: Record<Stats['zone'], string> = {
  inner_20m: 'Statistics exclude the 20 m field edge.',
  inner_10m: 'Statistics exclude the 10 m field edge.',
  full_field_fallback: 'Field too narrow to exclude the edge: statistics use the whole field.',
  full_field_all_touched: 'Statistics use every pixel touching the field.',
}

export const DATA_SOURCE_LABEL: Record<string, string> = {
  sentinel2: 'Satellite images',
  weather: 'Weather',
  soilgrids: 'SoilGrids',
  nibis: 'Lower Saxony soil survey (LBEG NIBIS)',
  lagb: 'Saxony-Anhalt soil survey (LAGB)',
}
