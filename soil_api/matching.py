"""Matching of submitted features to precomputed store fields."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
import sqlite3
from typing import Optional, Union

from shapely.geometry import shape

from .models import Feature, Geometry, MatchType
from .store import (
    FieldRecord,
    get_all_fields,
    get_coverage_area,
    get_field_by_geometry_hash,
    get_field_by_plot_id,
)


GEOMETRY_MATCH_IOU_THRESHOLD = 0.95


@dataclass(frozen=True)
class FieldMatch:
    """The result of matching one submitted feature to a known field."""

    feature_id: Optional[Union[str, int]]
    matched_plot_id: Optional[str]
    match: Optional[MatchType]
    field: Optional[FieldRecord]
    iou: Optional[float]


@dataclass(frozen=True)
class MatchMetadata:
    """Public field metadata resulting from matching and coverage checks."""

    feature_id: Optional[Union[str, int]]
    matched_plot_id: Optional[str]
    match: MatchType
    field_name: Optional[str]
    bounds: Optional[list[list[float]]]


def geometry_hash(geometry: Geometry) -> str:
    """Return the store-compatible hash of a longitude/latitude geometry."""

    def round_coordinates(coordinates: object) -> object:
        if (
            isinstance(coordinates, (list, tuple))
            and coordinates
            and isinstance(coordinates[0], (list, tuple))
        ):
            return [round_coordinates(value) for value in coordinates]
        if isinstance(coordinates, (list, tuple)) and len(coordinates) == 2:
            return [round(float(coordinates[0]), 6), round(float(coordinates[1]), 6)]
        raise ValueError("geometry coordinates have an unsupported structure")

    payload = {
        "type": geometry.type,
        "coordinates": round_coordinates(geometry.coordinates),
    }
    return hashlib.sha1(json.dumps(payload).encode()).hexdigest()[:16]


def _intersection_over_union(feature: Feature, field: FieldRecord) -> float:
    submitted_geometry = shape(feature.geometry.model_dump())
    stored_geometry = shape(field.geometry)
    union_area = submitted_geometry.union(stored_geometry).area
    if union_area == 0:
        return 0.0
    return float(submitted_geometry.intersection(stored_geometry).area / union_area)


def match_feature(connection: sqlite3.Connection, feature: Feature) -> FieldMatch:
    """Match a feature using plot ID, geometry hash, then IoU precedence."""

    plot_id = feature.properties.plot_id
    if plot_id is not None:
        field = get_field_by_plot_id(connection, plot_id)
        if field is not None:
            iou = _intersection_over_union(feature, field)
            match = (
                MatchType.PLOT_ID
                if iou >= GEOMETRY_MATCH_IOU_THRESHOLD
                else MatchType.PLOT_ID_GEOMETRY_DIFFERS
            )
            return FieldMatch(feature.id, field.plot_id, match, field, iou)

    matched_by_hash = get_field_by_geometry_hash(connection, geometry_hash(feature.geometry))
    if matched_by_hash is not None:
        return FieldMatch(feature.id, matched_by_hash.plot_id, MatchType.GEOMETRY, matched_by_hash, 1.0)

    best_match: Optional[tuple[FieldRecord, float]] = None
    for field in get_all_fields(connection):
        iou = _intersection_over_union(feature, field)
        if iou >= GEOMETRY_MATCH_IOU_THRESHOLD and (
            best_match is None or iou > best_match[1]
        ):
            best_match = (field, iou)

    if best_match is None:
        return FieldMatch(feature.id, None, None, None, None)
    field, iou = best_match
    return FieldMatch(feature.id, field.plot_id, MatchType.GEOMETRY, field, iou)


def _bounds_in_latitude_longitude_order(feature: Feature) -> list[list[float]]:
    """Convert Shapely's (min longitude, min latitude, ...) bounds."""

    minimum_longitude, minimum_latitude, maximum_longitude, maximum_latitude = shape(
        feature.geometry.model_dump()
    ).bounds
    return [
        [minimum_latitude, minimum_longitude],
        [maximum_latitude, maximum_longitude],
    ]


def classify_field_match(
    connection: sqlite3.Connection,
    feature: Feature,
    field_match: Optional[FieldMatch] = None,
) -> MatchMetadata:
    """Classify a match as known, clipped within coverage, or outside coverage."""

    resolved_match = field_match or match_feature(connection, feature)
    if resolved_match.field is not None and resolved_match.match is not None:
        return MatchMetadata(
            feature_id=resolved_match.feature_id,
            matched_plot_id=resolved_match.field.plot_id,
            match=resolved_match.match,
            field_name=resolved_match.field.field_name,
            bounds=resolved_match.field.bounds,
        )

    coverage_area = get_coverage_area(connection)
    if coverage_area is not None and shape(coverage_area.geometry).covers(
        shape(feature.geometry.model_dump())
    ):
        return MatchMetadata(
            feature_id=resolved_match.feature_id,
            matched_plot_id=None,
            match=MatchType.CLIPPED,
            field_name=None,
            bounds=_bounds_in_latitude_longitude_order(feature),
        )

    return MatchMetadata(
        feature_id=resolved_match.feature_id,
        matched_plot_id=None,
        match=MatchType.OUTSIDE_COVERAGE_AREA,
        field_name=None,
        bounds=None,
    )
