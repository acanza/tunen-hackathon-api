"""Typed read queries for the frozen soil metadata store."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple, Union


JsonObject = dict[str, Any]


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    created_at: str
    data_as_of: JsonObject
    notes: Optional[str]


@dataclass(frozen=True)
class SourceParameterRecord:
    source: str
    parameter: str
    method: Optional[str]


@dataclass(frozen=True)
class ColormapRecord:
    colormap_id: str
    definition: JsonObject


@dataclass(frozen=True)
class FieldRecord:
    plot_id: str
    field_name: str
    area_ha: float
    use_for_stats: bool
    state: str
    geom_hash: str
    geometry: JsonObject
    bounds: list[list[float]]
    inner20m_area_ha: Optional[float]
    flags: Optional[str]


@dataclass(frozen=True)
class FieldLayerRecord:
    run_id: str
    plot_id: str
    parameter: str
    source: str
    status: str
    reason: Optional[str]
    coverage: float
    unit: Optional[str]
    colormap_id: Optional[str]
    stats_zone: Optional[str]
    stats: Optional[JsonObject]
    confidence: Optional[JsonObject]
    geotiff_path: Optional[str]
    png_path: Optional[str]
    conf_png_path: Optional[str]
    provenance: Optional[JsonObject]


@dataclass(frozen=True)
class CoverageAreaRecord:
    name: str
    geometry: JsonObject
    notes: Optional[str]


def _row_mapping(
    row: Union[sqlite3.Row, Tuple[Any, ...]],
    columns: Tuple[str, ...],
) -> Mapping[str, Any]:
    if isinstance(row, sqlite3.Row):
        return row
    return dict(zip(columns, row))


def _query_rows(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...] = ()) -> list[Mapping[str, Any]]:
    cursor = connection.execute(query, parameters)
    columns = tuple(column[0] for column in cursor.description or ())
    return [_row_mapping(row, columns) for row in cursor.fetchall()]


def _parse_json_object(value: Optional[str], field_name: str) -> Optional[JsonObject]:
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must contain a JSON object")
    return parsed


def get_current_run(connection: sqlite3.Connection) -> RunRecord:
    """Return the single run marked as current."""

    rows = _query_rows(
        connection,
        """
        SELECT run_id, created_at, data_as_of_json, notes
        FROM runs
        WHERE is_current = 1
        """,
    )
    if len(rows) != 1:
        raise LookupError(f"Expected exactly one current run, found {len(rows)}")
    row = rows[0]
    data_as_of = _parse_json_object(row["data_as_of_json"], "runs.data_as_of_json")
    assert data_as_of is not None
    return RunRecord(
        run_id=str(row["run_id"]),
        created_at=str(row["created_at"]),
        data_as_of=data_as_of,
        notes=row["notes"],
    )


def get_source_parameters(connection: sqlite3.Connection) -> Tuple[SourceParameterRecord, ...]:
    """Return the supported parameter/source pairs in store order."""

    return tuple(
        SourceParameterRecord(
            source=str(row["source"]),
            parameter=str(row["parameter"]),
            method=row["method"],
        )
        for row in _query_rows(
            connection,
            "SELECT source, parameter, method FROM source_parameters ORDER BY rowid",
        )
    )


def get_colormaps(connection: sqlite3.Connection) -> dict[str, ColormapRecord]:
    """Return all stored colour map definitions keyed by identifier."""

    records: dict[str, ColormapRecord] = {}
    for row in _query_rows(connection, "SELECT colormap_id, json FROM colormaps ORDER BY colormap_id"):
        colormap_id = str(row["colormap_id"])
        definition = _parse_json_object(row["json"], f"colormaps[{colormap_id}].json")
        assert definition is not None
        records[colormap_id] = ColormapRecord(colormap_id=colormap_id, definition=definition)
    return records


def _field_from_row(row: Mapping[str, Any]) -> FieldRecord:
    geometry = _parse_json_object(row["geom_geojson"], "fields.geom_geojson")
    bounds = json.loads(row["bounds_json"])
    if not isinstance(bounds, list):
        raise ValueError("fields.bounds_json must contain a JSON array")
    assert geometry is not None
    return FieldRecord(
        plot_id=str(row["plot_id"]),
        field_name=str(row["field_name"]),
        area_ha=float(row["area_ha"]),
        use_for_stats=bool(row["use_for_stats"]),
        state=str(row["state"]),
        geom_hash=str(row["geom_hash"]),
        geometry=geometry,
        bounds=bounds,
        inner20m_area_ha=row["inner20m_area_ha"],
        flags=row["flags"],
    )


def get_field_by_plot_id(connection: sqlite3.Connection, plot_id: str) -> Optional[FieldRecord]:
    """Return a known field by its stable plot identifier."""

    rows = _query_rows(
        connection,
        "SELECT * FROM fields WHERE plot_id = ?",
        (plot_id,),
    )
    return _field_from_row(rows[0]) if rows else None


def get_field_by_geometry_hash(connection: sqlite3.Connection, geom_hash: str) -> Optional[FieldRecord]:
    """Return a known field by its precomputed geometry hash."""

    rows = _query_rows(
        connection,
        "SELECT * FROM fields WHERE geom_hash = ?",
        (geom_hash,),
    )
    return _field_from_row(rows[0]) if rows else None


def get_field_layers(
    connection: sqlite3.Connection,
    run_id: str,
    plot_id: str,
) -> Tuple[FieldLayerRecord, ...]:
    """Return every stored layer for one field and run."""

    records = []
    for row in _query_rows(
        connection,
        """
        SELECT run_id, plot_id, parameter, source, status, reason, coverage,
               unit, colormap_id, stats_zone, stats_json, confidence_json,
               geotiff_path, png_path, conf_png_path, provenance_json
        FROM field_layers
        WHERE run_id = ? AND plot_id = ?
        ORDER BY parameter, source
        """,
        (run_id, plot_id),
    ):
        records.append(
            FieldLayerRecord(
                run_id=str(row["run_id"]),
                plot_id=str(row["plot_id"]),
                parameter=str(row["parameter"]),
                source=str(row["source"]),
                status=str(row["status"]),
                reason=row["reason"],
                coverage=float(row["coverage"]),
                unit=row["unit"],
                colormap_id=row["colormap_id"],
                stats_zone=row["stats_zone"],
                stats=_parse_json_object(row["stats_json"], "field_layers.stats_json"),
                confidence=_parse_json_object(row["confidence_json"], "field_layers.confidence_json"),
                geotiff_path=row["geotiff_path"],
                png_path=row["png_path"],
                conf_png_path=row["conf_png_path"],
                provenance=_parse_json_object(row["provenance_json"], "field_layers.provenance_json"),
            )
        )
    return tuple(records)


def get_coverage_area(
    connection: sqlite3.Connection,
    name: str = "farm_raster_extent",
) -> Optional[CoverageAreaRecord]:
    """Return a named coverage polygon from the store."""

    rows = _query_rows(
        connection,
        "SELECT name, geom_geojson, notes FROM coverage_areas WHERE name = ?",
        (name,),
    )
    if not rows:
        return None
    row = rows[0]
    geometry = _parse_json_object(row["geom_geojson"], "coverage_areas.geom_geojson")
    assert geometry is not None
    return CoverageAreaRecord(name=str(row["name"]), geometry=geometry, notes=row["notes"])
