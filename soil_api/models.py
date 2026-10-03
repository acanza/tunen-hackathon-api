"""Request models and validation for the frozen soil layers POC."""

from __future__ import annotations

import math
from enum import Enum
from typing import Any, ClassVar, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from shapely.geometry import shape
from shapely.validation import explain_validity


class Parameter(str, Enum):
    """Parameters exposed by the frozen store."""

    TEXTURE = "texture"
    PH = "ph"
    SOC = "soc"
    NFK = "nfk"
    BODENZAHL = "bodenzahl"
    YIELD_POTENTIAL = "yield_potential"


class Source(str, Enum):
    """Sources exposed by the frozen store."""

    SOILGRIDS = "soilgrids"
    LBEG_BK50 = "lbeg_bk50"
    LBEG_BODENSCHAETZUNG = "lbeg_bodenschaetzung"
    DERIVED = "derived"


class Geometry(BaseModel):
    """A GeoJSON Polygon or MultiPolygon in longitude/latitude order."""

    model_config = ConfigDict(extra="forbid")

    type: str
    coordinates: list[Any]

    _supported_types: ClassVar[frozenset[str]] = frozenset({"Polygon", "MultiPolygon"})

    @model_validator(mode="after")
    def validate_geometry(self) -> "Geometry":
        if self.type not in self._supported_types:
            raise ValueError("geometry.type must be Polygon or MultiPolygon")

        try:
            parsed = shape(self.model_dump())
            bounds = parsed.bounds
            finite_bounds = all(math.isfinite(value) for value in bounds)
        except (TypeError, ValueError) as error:
            raise ValueError("geometry.coordinates must be valid GeoJSON") from error

        if parsed.is_empty or not parsed.is_valid:
            detail = explain_validity(parsed)
            raise ValueError(f"geometry must be a non-empty valid polygon: {detail}")
        if not finite_bounds:
            raise ValueError("geometry coordinates must be finite numbers")
        if not (-180 <= bounds[0] <= bounds[2] <= 180):
            raise ValueError("geometry longitude must be between -180 and 180")
        if not (-90 <= bounds[1] <= bounds[3] <= 90):
            raise ValueError("geometry latitude must be between -90 and 90")
        return self


class FeatureProperties(BaseModel):
    """Optional identifiers used by field matching, plus client metadata."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    plot_id: Optional[str] = Field(default=None, alias="plotId")
    field_name: Optional[str] = Field(default=None, alias="fieldName")

    @field_validator("plot_id", "field_name")
    @classmethod
    def validate_identifier(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("feature identifiers must not be empty")
        return value


class Feature(BaseModel):
    """A request feature containing one field geometry."""

    model_config = ConfigDict(extra="forbid")

    type: str
    id: Optional[Union[str, int]] = None
    properties: FeatureProperties = Field(default_factory=FeatureProperties)
    geometry: Geometry

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != "Feature":
            raise ValueError("feature.type must be Feature")
        return value


class LayersRequest(BaseModel):
    """Request payload for POST /soil/layers."""

    model_config = ConfigDict(extra="forbid")

    type: str
    features: list[Feature]
    parameters: Optional[list[Parameter]] = None
    sources: Optional[list[Source]] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        if value != "FeatureCollection":
            raise ValueError("request.type must be FeatureCollection")
        return value

    @field_validator("features")
    @classmethod
    def validate_feature_limit(cls, value: list[Feature]) -> list[Feature]:
        if len(value) > 200:
            raise ValueError("a maximum of 200 features is supported")
        return value

    @field_validator("parameters", "sources")
    @classmethod
    def reject_duplicate_filters(
        cls,
        value: Optional[list[Enum]],
    ) -> Optional[list[Enum]]:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("filter values must be unique")
        return value

    @property
    def requested_parameters(self) -> Optional[tuple[Parameter, ...]]:
        """Return an immutable filter, preserving omission as ``None``."""

        return tuple(self.parameters) if self.parameters is not None else None

    @property
    def requested_sources(self) -> Optional[tuple[Source, ...]]:
        """Return an immutable filter, preserving omission as ``None``."""

        return tuple(self.sources) if self.sources is not None else None
