"""Internal M1 domain models and validation.

This module deliberately contains no FastAPI routes, provider access, raster
processing, or rendering. Unit 1B consumes this contract.
"""

from enum import Enum
from math import ceil
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from shapely.geometry import shape
from shapely.validation import explain_validity


FIELD_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
FieldIdentifier = Annotated[str, StringConstraints(pattern=FIELD_IDENTIFIER_PATTERN)]
Position = tuple[float, float]
LinearRing = list[Position]
PolygonCoordinates = list[LinearRing]
MultiPolygonCoordinates = list[PolygonCoordinates]


class DomainModel(BaseModel):
    """Strict base for internal models; Python identifiers stay snake_case."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Parameter(str, Enum):
    CLAY = "clay"


class Source(str, Enum):
    SOILGRIDS = "soilgrids"


class ResultStatus(str, Enum):
    AVAILABLE = "available"
    UNSUPPORTED = "unsupported"
    OUTSIDE_COVERAGE = "outside_coverage"
    NO_DATA = "no_data"
    FAILED = "failed"


class BatchStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    FAILED = "failed"


class ErrorCode(str, Enum):
    UNSUPPORTED_REQUEST = "unsupported_request"
    OUTSIDE_COVERAGE = "outside_coverage"
    NO_DATA = "no_data"
    PROVIDER_FAILURE = "provider_failure"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROCESSING_FAILURE = "processing_failure"


class ArtifactKind(str, Enum):
    PNG = "png"
    JSON_GRID = "json_grid"


class GeoJsonPolygon(DomainModel):
    type: Literal["Polygon"]
    coordinates: PolygonCoordinates


class GeoJsonMultiPolygon(DomainModel):
    type: Literal["MultiPolygon"]
    coordinates: MultiPolygonCoordinates


SupportedGeometry = Annotated[
    Union[GeoJsonPolygon, GeoJsonMultiPolygon], Field(discriminator="type")
]


class GeoJsonFeature(DomainModel):
    type: Literal["Feature"]
    id: FieldIdentifier
    geometry: SupportedGeometry
    properties: dict[str, Any] = Field(default_factory=dict)


class GeoJsonFeatureCollection(DomainModel):
    type: Literal["FeatureCollection"]
    features: list[GeoJsonFeature]


class DepthRange(DomainModel):
    top_cm: Literal[0] = 0
    bottom_cm: Literal[30] = 30


class ProcessingLimits(DomainModel):
    max_fields: int = 2
    max_area_hectares: float = 1_000.0
    max_vertices: int = 5_000
    max_output_pixels: int = 4_096
    max_provider_calls: int = 16
    max_concurrency: int = 2
    max_total_output_pixels: int = 8_192
    max_retry_attempts: int = 2
    connect_timeout_seconds: float = 10.0
    provider_timeout_seconds: float = 45.0
    processing_timeout_seconds: float = 30.0


DEFAULT_PROCESSING_LIMITS = ProcessingLimits()
PROVIDER_CALLS_PER_CLAY_FIELD = 8


def _iter_rings(geometry: SupportedGeometry):
    polygons = (
        [geometry.coordinates]
        if isinstance(geometry, GeoJsonPolygon)
        else geometry.coordinates
    )
    for polygon in polygons:
        for ring in polygon:
            yield ring


def _count_vertices(geometry: SupportedGeometry) -> int:
    return sum(len(ring) for ring in _iter_rings(geometry))


def _validate_positions(geometry: SupportedGeometry) -> None:
    polygon_count = (
        1 if isinstance(geometry, GeoJsonPolygon) else len(geometry.coordinates)
    )
    if polygon_count == 0:
        raise ValueError("geometry must contain at least one polygon")
    for ring in _iter_rings(geometry):
        if len(ring) < 4:
            raise ValueError("each linear ring must contain at least four positions")
        if ring[0] != ring[-1]:
            raise ValueError("each linear ring must be closed")
        for longitude, latitude in ring:
            if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                raise ValueError(
                    "GeoJSON positions must use longitude/latitude within valid ranges"
                )


def _geodesic_area_hectares(geometry: SupportedGeometry) -> float:
    """Approximate bounded validation area using a local equal-area projection.

    Shapely operates on longitude/latitude here. A Lambert azimuthal equal-area
    projection centered on the geometry provides stable validation for the
    intentionally bounded field sizes in M1 without treating degrees as metres.
    """

    from pyproj import CRS, Transformer
    from shapely.ops import transform

    shaped_geometry = shape(geometry.model_dump())
    center = shaped_geometry.centroid
    local_equal_area = CRS.from_proj4(
        f"+proj=laea +lat_0={center.y} +lon_0={center.x} +datum=WGS84 +units=m +no_defs"
    )
    transformer = Transformer.from_crs("EPSG:4326", local_equal_area, always_xy=True)
    return transform(transformer.transform, shaped_geometry).area / 10_000


class LayerRequest(DomainModel):
    fields: GeoJsonFeatureCollection
    parameters: tuple[Parameter, ...] = (Parameter.CLAY,)
    sources: tuple[Source, ...] = (Source.SOILGRIDS,)
    depth: DepthRange = Field(default_factory=DepthRange)
    output_resolution_meters: float = Field(default=250.0, gt=0)

    @model_validator(mode="after")
    def validate_bounded_request(self):
        limits = DEFAULT_PROCESSING_LIMITS
        if not self.fields.features:
            raise ValueError("request requires at least one field")
        if len(self.fields.features) > limits.max_fields:
            raise ValueError(
                f"request has {len(self.fields.features)} fields; maximum is "
                f"{limits.max_fields}"
            )
        field_ids = [feature.id for feature in self.fields.features]
        if len(field_ids) != len(set(field_ids)):
            raise ValueError("request requires exactly one field identifier per field")
        if self.parameters != (Parameter.CLAY,):
            raise ValueError("M1 supports only the clay parameter")
        if self.sources != (Source.SOILGRIDS,):
            raise ValueError("M1 supports only the soilgrids source")
        estimated_provider_calls = len(self.fields.features) * PROVIDER_CALLS_PER_CLAY_FIELD
        if estimated_provider_calls > limits.max_provider_calls:
            raise ValueError(
                f"request estimates {estimated_provider_calls} provider calls; "
                f"maximum is {limits.max_provider_calls}"
            )

        total_pixels = 0
        for feature in self.fields.features:
            geometry = feature.geometry
            _validate_positions(geometry)
            vertex_count = _count_vertices(geometry)
            if vertex_count > limits.max_vertices:
                raise ValueError(
                    f"field {feature.id} has {vertex_count} vertices; maximum is "
                    f"{limits.max_vertices}"
                )

            shaped_geometry = shape(geometry.model_dump())
            if shaped_geometry.is_empty:
                raise ValueError(f"field {feature.id} geometry must not be empty")
            if not shaped_geometry.is_valid:
                raise ValueError(
                    f"invalid field geometry for {feature.id}: "
                    f"{explain_validity(shaped_geometry)}"
                )

            area_hectares = _geodesic_area_hectares(geometry)
            if area_hectares <= 0:
                raise ValueError(f"field {feature.id} area must be greater than zero")
            if area_hectares > limits.max_area_hectares:
                raise ValueError(
                    f"field {feature.id} area {area_hectares:.3f} ha exceeds "
                    f"{limits.max_area_hectares:.3f} ha"
                )

            west, south, east, north = shaped_geometry.bounds
            width = max(1, ceil((east - west) * 111_320 / self.output_resolution_meters))
            height = max(1, ceil((north - south) * 111_320 / self.output_resolution_meters))
            estimated_pixels = width * height
            if estimated_pixels > limits.max_output_pixels:
                raise ValueError(
                    f"estimated output grid for {feature.id} has {estimated_pixels} "
                    f"pixels; maximum is {limits.max_output_pixels}"
                )
            total_pixels += estimated_pixels
        if total_pixels > limits.max_total_output_pixels:
            raise ValueError(
                f"request estimates {total_pixels} output pixels; maximum is "
                f"{limits.max_total_output_pixels}"
            )
        return self


class CoordinateBounds(DomainModel):
    west: float
    south: float
    east: float
    north: float

    @model_validator(mode="after")
    def validate_order(self):
        if self.west >= self.east or self.south >= self.north:
            raise ValueError("bounds require west < east and south < north")
        return self

    def as_wsen(self) -> tuple[float, float, float, float]:
        return self.west, self.south, self.east, self.north


class GridDefinition(DomainModel):
    crs: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    transform: tuple[float, float, float, float, float, float]
    bounds: CoordinateBounds
    row_order: Literal["north_to_south"] = "north_to_south"
    column_order: Literal["west_to_east"] = "west_to_east"
    null_value: None = None


class LayerStatistics(DomainModel):
    valid_pixel_count: int = Field(ge=1)
    minimum: float
    mean: float
    maximum: float

    @model_validator(mode="after")
    def validate_order(self):
        if not self.minimum <= self.mean <= self.maximum:
            raise ValueError("statistics require minimum <= mean <= maximum")
        return self


class ArtifactReference(DomainModel):
    artifact_id: str = Field(min_length=1, max_length=128)
    kind: ArtifactKind
    media_type: str = Field(min_length=1, max_length=128)


class LegendEntry(DomainModel):
    value: float
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class LayerData(DomainModel):
    field_id: FieldIdentifier
    parameter: Literal[Parameter.CLAY]
    source: Literal[Source.SOILGRIDS]
    unit: Literal["percent"]
    depth: DepthRange
    grid: GridDefinition
    statistics: LayerStatistics
    artifacts: tuple[ArtifactReference, ArtifactReference]
    retrieved_at: str
    dataset_version: Optional[str]
    dataset_date: Optional[str]
    method: str = Field(min_length=1)
    legend: tuple[LegendEntry, ...] = ()
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_artifacts(self):
        kinds = {artifact.kind for artifact in self.artifacts}
        if kinds != {ArtifactKind.PNG, ArtifactKind.JSON_GRID}:
            raise ValueError("available layers require one PNG and one JSON grid")
        return self


class LayerError(DomainModel):
    code: ErrorCode
    message: str = Field(min_length=1)
    retryable: bool = False


class LayerResult(DomainModel):
    status: ResultStatus
    data: Optional[LayerData] = None
    error: Optional[LayerError] = None

    @model_validator(mode="after")
    def validate_status_payload(self):
        if self.status == ResultStatus.AVAILABLE:
            if self.data is None or self.error is not None:
                raise ValueError("available result requires data and forbids error")
        elif self.data is not None or self.error is None:
            raise ValueError("non-available result requires error and forbids data")
        return self


class FieldLayerResult(DomainModel):
    field_id: FieldIdentifier
    parameter: Literal[Parameter.CLAY]
    source: Literal[Source.SOILGRIDS]
    result: LayerResult


class LayerBatchResult(DomainModel):
    status: BatchStatus
    results: tuple[FieldLayerResult, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_status(self):
        statuses = {item.result.status for item in self.results}
        if self.status == BatchStatus.AVAILABLE and statuses != {ResultStatus.AVAILABLE}:
            raise ValueError("available batch requires all results to be available")
        if self.status == BatchStatus.PARTIAL and (
            ResultStatus.AVAILABLE not in statuses or len(statuses) < 2
        ):
            raise ValueError("partial batch requires both available and failed results")
        if self.status == BatchStatus.FAILED and ResultStatus.AVAILABLE in statuses:
            raise ValueError("failed batch cannot contain available results")
        return self
