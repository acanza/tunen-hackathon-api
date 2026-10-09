"""Requested parameter/source matrix expansion for the frozen store."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, TypeVar

from .models import LayerStatus, LayersRequest, Parameter, Source
from .store import SourceParameterRecord


ValueType = TypeVar("ValueType")


@dataclass(frozen=True)
class RequestedLayerPair:
    """One stable parameter/source request with its applicability."""

    parameter: Parameter
    source: Source
    status: Optional[LayerStatus] = None
    reason: Optional[str] = None


def _ordered_unique(values: Iterable[ValueType]) -> tuple[ValueType, ...]:
    """Return values once, preserving their first-seen order."""

    return tuple(dict.fromkeys(values))


def expand_requested_layer_pairs(
    request: LayersRequest,
    supported_pairs: Iterable[SourceParameterRecord],
) -> tuple[RequestedLayerPair, ...]:
    """Expand request filters into a stable parameter-major matrix.

    Omitted filters use the values present in ``source_parameters``. Explicit
    filters retain their request order, including values not supported by the
    store, so those pairs can be returned as ``not_applicable``.
    """

    records = tuple(supported_pairs)
    normalized_pairs = {
        (Parameter(record.parameter), Source(record.source))
        for record in records
    }

    parameters = request.requested_parameters
    if parameters is None:
        parameters = _ordered_unique(Parameter(record.parameter) for record in records)

    sources = request.requested_sources
    if sources is None:
        sources = _ordered_unique(Source(record.source) for record in records)

    expanded_pairs: list[RequestedLayerPair] = []
    for parameter in parameters:
        for source in sources:
            if (parameter, source) in normalized_pairs:
                expanded_pairs.append(
                    RequestedLayerPair(parameter=parameter, source=source)
                )
            else:
                expanded_pairs.append(
                    RequestedLayerPair(
                        parameter=parameter,
                        source=source,
                        status=LayerStatus.NOT_APPLICABLE,
                        reason="source_does_not_provide_parameter",
                    )
                )
    return tuple(expanded_pairs)
