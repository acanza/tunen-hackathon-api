"""Mapping of stored layer metadata to the public response model."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Mapping, Optional

from .models import ConfidenceResponse, LayerResponse, LayerStatus, Parameter, Source
from .store import ColormapRecord, FieldLayerRecord


def _static_url(relative_path: Optional[str]) -> Optional[str]:
    """Create a safe URL for a store-relative artifact path."""

    if relative_path is None:
        return None
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"artifact path must be relative to the store: {relative_path}")
    return f"/static/{path.as_posix()}"


def _confidence_response(
    layer: FieldLayerRecord,
) -> Optional[ConfidenceResponse]:
    if layer.confidence is None:
        return None
    confidence = dict(layer.confidence)
    raster_url = _static_url(layer.geotiff_path)
    if raster_url is not None:
        confidence["raster_url"] = f"{raster_url}#band=4"
    confidence["png_url"] = _static_url(layer.conf_png_path)
    return ConfidenceResponse.model_validate(confidence)


def map_field_layer(
    layer: FieldLayerRecord,
    colormaps: Mapping[str, ColormapRecord],
) -> LayerResponse:
    """Map one stored layer and its colormap to the public response model."""

    status = LayerStatus(layer.status)
    common = {
        "parameter": Parameter(layer.parameter),
        "source": Source(layer.source),
        "status": status,
        "reason": layer.reason,
        "coverage": layer.coverage,
        "unit": layer.unit,
    }

    if status not in (LayerStatus.OK, LayerStatus.PARTIAL):
        return LayerResponse(**common)

    colormap = None
    if layer.colormap_id is not None:
        try:
            colormap = colormaps[layer.colormap_id].definition
        except KeyError as error:
            raise LookupError(
                f"Missing colormap {layer.colormap_id!r} for "
                f"{layer.parameter}/{layer.source}"
            ) from error

    return LayerResponse(
        **common,
        png_url=_static_url(layer.png_path),
        geotiff_url=_static_url(layer.geotiff_path),
        stats=layer.stats,
        colormap=colormap,
        confidence=_confidence_response(layer),
        provenance=layer.provenance,
    )
