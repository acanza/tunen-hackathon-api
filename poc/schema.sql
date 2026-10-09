-- POC store for the soil layers API. Pixels live in files under poc/store/; this DB holds metadata only.
-- Geometries are GeoJSON text in EPSG:4326 (no SpatiaLite needed). Paths are relative to poc/store/.

DROP TABLE IF EXISTS validation;
DROP TABLE IF EXISTS field_layers;
DROP TABLE IF EXISTS fields;
DROP TABLE IF EXISTS regional_rasters;
DROP TABLE IF EXISTS coverage_areas;
DROP TABLE IF EXISTS colormaps;
DROP TABLE IF EXISTS source_parameters;
DROP TABLE IF EXISTS parameters;
DROP TABLE IF EXISTS sources;
DROP TABLE IF EXISTS runs;

-- One row per pipeline run. The API serves the run with is_current = 1.
CREATE TABLE runs (
    run_id          TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,           -- ISO 8601 UTC
    is_current      INTEGER NOT NULL,        -- exactly one row = 1
    data_as_of_json TEXT NOT NULL,           -- {"sentinel2": "...", "weather": "...", ...}
    notes           TEXT
);

CREATE TABLE sources (
    source              TEXT PRIMARY KEY,    -- soilgrids | lbeg_bk50 | lbeg_bodenschaetzung | derived
    label               TEXT NOT NULL,
    scale               TEXT,
    native_resolution_m REAL,
    region              TEXT,                -- where the source exists at all
    licence             TEXT,
    pulled              TEXT
);

CREATE TABLE parameters (
    parameter   TEXT PRIMARY KEY,            -- texture | ph | soc | nfk | bodenzahl | yield_potential
    label       TEXT NOT NULL,
    description TEXT
);

-- Which source can deliver which parameter. A requested pair not listed here → status "not_applicable".
CREATE TABLE source_parameters (
    source    TEXT NOT NULL REFERENCES sources(source),
    parameter TEXT NOT NULL REFERENCES parameters(parameter),
    method    TEXT,
    PRIMARY KEY (source, parameter)
);

-- Fixed colour scale per parameter (same for every field). Returned verbatim as "colormap".
CREATE TABLE colormaps (
    colormap_id TEXT PRIMARY KEY,
    json        TEXT NOT NULL
);

-- Farm-wide rasters (EPSG:32632, 10 m). Used to clip polygons that are not known fields.
-- Bands: 1 value, 2 lo90, 3 hi90, 4 confidence (1 low, 2 medium, 3 high); source=best adds
-- 5 source_code (codes in the file's `source_codes` tag). Nodata = NaN.
CREATE TABLE regional_rasters (
    run_id      TEXT NOT NULL REFERENCES runs(run_id),
    parameter   TEXT NOT NULL,
    source      TEXT NOT NULL,
    path        TEXT NOT NULL,
    kind        TEXT NOT NULL,               -- continuous | categorical
    unit        TEXT,
    colormap_id TEXT REFERENCES colormaps(colormap_id),
    PRIMARY KEY (run_id, parameter, source)
);

-- Areas the API can answer for. A polygon not inside 'farm_raster_extent' → "outside_coverage_area".
CREATE TABLE coverage_areas (
    name          TEXT PRIMARY KEY,
    geom_geojson  TEXT NOT NULL,
    notes         TEXT
);

-- Known fields (from data/seggerde/clean/fields_clean.geojson).
CREATE TABLE fields (
    plot_id          TEXT PRIMARY KEY,
    field_name       TEXT NOT NULL,
    area_ha          REAL NOT NULL,
    use_for_stats    INTEGER NOT NULL,       -- 0 = sliver/overlap remnant; no yield potential
    state            TEXT NOT NULL,          -- NI (Niedersachsen, NIBIS data) | ST (Sachsen-Anhalt)
    geom_hash        TEXT NOT NULL,          -- sha1 of coordinates rounded to 6 decimals, 16 hex chars
    geom_geojson     TEXT NOT NULL,          -- EPSG:4326
    bounds_json      TEXT NOT NULL,          -- [[S,W],[N,E]] of the PNG overlays (Leaflet imageOverlay)
    inner20m_area_ha REAL,
    flags            TEXT
);
CREATE INDEX fields_geom_hash ON fields(geom_hash);

-- One row per run × field × (parameter, source) the source can deliver, including unavailable ones.
CREATE TABLE field_layers (
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    plot_id         TEXT NOT NULL REFERENCES fields(plot_id),
    parameter       TEXT NOT NULL,
    source          TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('ok', 'partial', 'unavailable')),
    reason          TEXT,                    -- machine-readable, set when status != 'ok'
    coverage        REAL NOT NULL,           -- share of the field the source covers, 0–1
    unit            TEXT,
    colormap_id     TEXT REFERENCES colormaps(colormap_id),
    stats_zone      TEXT,                    -- inner_20m | inner_10m | full_field_fallback | full_field_all_touched
    stats_json      TEXT,                    -- continuous: mean,std,min,p10,p50,p90,max,n_px; categorical: classes,dominant
    confidence_json TEXT,                    -- {level, interval_90, drivers, pixel_shares}
    geotiff_path    TEXT,                    -- 4-band COG (5 for source=best), EPSG:32632
    png_path        TEXT,                    -- RGBA, EPSG:3857, aligned to fields.bounds_json
    conf_png_path   TEXT,                    -- hatch over low-confidence pixels, same grid as png
    source_png_path TEXT,                    -- source=best only: which source won per pixel, same grid as png
    provenance_json TEXT,
    PRIMARY KEY (run_id, plot_id, parameter, source)
);

-- Written by poc/validate.py (run after build_store.py). Metrics for the derived layers.
CREATE TABLE validation (
    run_id       TEXT NOT NULL REFERENCES runs(run_id),
    metric       TEXT NOT NULL,
    scope        TEXT NOT NULL,
    value        REAL,
    n            INTEGER,
    details_json TEXT
);
