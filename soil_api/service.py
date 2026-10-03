"""Response orchestration for the frozen soil layers endpoint."""

from __future__ import annotations

import sqlite3
from typing import Optional

from .layers import map_field_layer
from .matching import classify_field_match
from .matrix import RequestedLayerPair, expand_requested_layer_pairs
from .models import (
    FieldResponse,
    Feature,
    LayerResponse,
    LayerStatus,
    LayersRequest,
    LayersResponse,
)
from .store import (
    FieldLayerRecord,
    get_colormaps,
    get_current_run,
    get_field_layers,
    get_source_parameters,
)


def _not_applicable_layer(pair: RequestedLayerPair) -> LayerResponse:
    if pair.status != LayerStatus.NOT_APPLICABLE:
        raise ValueError("only not-applicable pairs can use this layer builder")
    return LayerResponse(
        parameter=pair.parameter,
        source=pair.source,
        status=LayerStatus.NOT_APPLICABLE,
        reason=pair.reason,
    )


def _unavailable_layer(
    pair: RequestedLayerPair,
    reason: str,
    coverage: Optional[float] = None,
) -> LayerResponse:
    return LayerResponse(
        parameter=pair.parameter,
        source=pair.source,
        status=LayerStatus.UNAVAILABLE,
        reason=reason,
        coverage=coverage,
    )


def _stored_layers_by_pair(
    layers: tuple[FieldLayerRecord, ...],
) -> dict[tuple[str, str], FieldLayerRecord]:
    return {(layer.parameter, layer.source): layer for layer in layers}


def _build_field_response(
    connection: sqlite3.Connection,
    request_feature: Feature,
    pairs: tuple[RequestedLayerPair, ...],
    colormaps,
    run_id: str,
) -> FieldResponse:
    match_metadata = classify_field_match(connection, request_feature)
    stored_layers: dict[tuple[str, str], FieldLayerRecord] = {}
    if match_metadata.matched_plot_id is not None:
        stored_layers = _stored_layers_by_pair(
            get_field_layers(connection, run_id, match_metadata.matched_plot_id)
        )

    layers: list[LayerResponse] = []
    for pair in pairs:
        if pair.status == LayerStatus.NOT_APPLICABLE:
            layers.append(_not_applicable_layer(pair))
            continue
        if match_metadata.match.value == "outside_coverage_area":
            layers.append(_unavailable_layer(pair, "outside_coverage_area"))
            continue
        if match_metadata.match.value == "clipped":
            layers.append(_unavailable_layer(pair, "not_precomputed_for_this_polygon"))
            continue

        stored_layer = stored_layers.get((pair.parameter.value, pair.source.value))
        if stored_layer is None:
            layers.append(_unavailable_layer(pair, "no_data_in_source"))
        else:
            layers.append(map_field_layer(stored_layer, colormaps))

    return FieldResponse(
        id=request_feature.id,
        matched_plot_id=match_metadata.matched_plot_id,
        match=match_metadata.match,
        field_name=match_metadata.field_name,
        bounds=match_metadata.bounds,
        layers=layers,
    )


def assemble_layers_response(
    connection: sqlite3.Connection,
    request: LayersRequest,
) -> LayersResponse:
    """Build the complete response without provider calls or store writes."""

    run = get_current_run(connection)
    pairs = expand_requested_layer_pairs(request, get_source_parameters(connection))
    colormaps = get_colormaps(connection)
    fields = [
        _build_field_response(connection, feature, pairs, colormaps, run.run_id)
        for feature in request.features
    ]
    return LayersResponse(run_id=run.run_id, data_as_of=run.data_as_of, fields=fields)
