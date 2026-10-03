# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "pandas", "geopandas", "shapely", "pyproj", "pillow", "scipy", "scikit-learn", "lxml"]
# ///
"""Export mock API fixtures for the UI from the POC store (read-only).

    uv run ui/scripts/export_fixtures.py      # from the repo root

Writes ui/public/mock/:
- fields.geojson          what GET /soil/fields returns
- runs_current.json       what GET /soil/runs/current returns
- meta.json               sources, source_parameters, validation, runs (proposed GET /soil/meta)
- layers/<plotId>.json    one `fields[]` entry of POST /soil/layers per known field, all parameters x sources

Uses assemble_response() from poc/build_store.py so the mock is the contract, not a copy of it.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "poc"))
from build_store import PARAMETERS, SOURCES, assemble_response  # noqa: E402

DB = ROOT / "poc" / "store" / "soil.sqlite"
OUT = ROOT / "ui" / "public" / "mock"


def rows(conn, sql, *args):
    return [dict(r) for r in conn.execute(sql, args)]


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    run = conn.execute("SELECT * FROM runs WHERE is_current = 1").fetchone()
    run_id = run["run_id"]
    params = [p[0] for p in PARAMETERS]
    sources = [s[0] for s in SOURCES]

    fields = rows(conn, "SELECT plot_id, field_name, area_ha, state, use_for_stats, geom_geojson FROM fields ORDER BY field_name")
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": f["plot_id"],
         "properties": {"plotId": f["plot_id"], "name": f["field_name"], "area_ha": f["area_ha"],
                        "state": f["state"], "use_for_stats": bool(f["use_for_stats"])},
         "geometry": json.loads(f["geom_geojson"])} for f in fields]}

    (OUT / "layers").mkdir(parents=True, exist_ok=True)
    (OUT / "fields.geojson").write_text(json.dumps(fc))
    data_as_of = json.loads(run["data_as_of_json"])
    (OUT / "runs_current.json").write_text(json.dumps({"run_id": run_id, "data_as_of": data_as_of}, indent=1))

    meta = {
        "run_id": run_id,
        "data_as_of": data_as_of,
        "runs": [r | {"data_as_of": json.loads(r.pop("data_as_of_json"))} for r in rows(conn, "SELECT * FROM runs")],
        "sources": rows(conn, "SELECT * FROM sources"),
        "parameters": rows(conn, "SELECT * FROM parameters"),
        "source_parameters": rows(conn, "SELECT * FROM source_parameters"),
        "validation": [v | {"details": json.loads(v.pop("details_json") or "null")}
                       for v in rows(conn, "SELECT metric, scope, value, n, details_json FROM validation WHERE run_id = ?", run_id)],
    }
    (OUT / "meta.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))

    req = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": f["plot_id"], "properties": {"plotId": f["plot_id"]}, "geometry": None} for f in fields]}
    resp = assemble_response(conn, req, params, sources)
    for entry in resp["fields"]:
        (OUT / "layers" / f"{entry['matched_plot_id']}.json").write_text(json.dumps(entry, ensure_ascii=False))
    print(f"{len(fields)} fields, {len(params)} parameters x {len(sources)} sources -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
