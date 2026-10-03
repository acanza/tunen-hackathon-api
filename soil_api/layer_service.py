"""M1 single-field layer coordination, processing, and artifact storage."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import uuid

import numpy as np
import rasterio
from rasterio.io import MemoryFile

from soil_api.domain import (
    ArtifactKind,
    ArtifactReference,
    LayerData,
    LayerError,
    LayerRequest,
    LayerResult,
    LayerStatistics,
    LegendEntry,
    ResultStatus,
)
from soil_api.providers.soilgrids import (
    SoilGridsAdapter,
    SoilGridsProviderError,
    SoilGridsProviderTimeout,
)


CLAY_METHOD = (
    "(5*c0_5 + 10*c5_15 + 15*c15_30) / 3000; "
    "inputs in g/kg, output in percent; all three intervals required"
)
LEGEND_COLORS = ("#2166AC", "#F7F7F7", "#B2182B")


class ArtifactStore:
    """Local immutable storage for the two M1 layer artifacts."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, suffix: str, payload: bytes) -> str:
        artifact_id = uuid.uuid4().hex
        path = self.root / f"{artifact_id}.{suffix}"
        path.write_bytes(payload)
        return artifact_id

    def get(self, artifact_id: str, kind: ArtifactKind) -> bytes:
        suffix = "png" if kind == ArtifactKind.PNG else "json"
        path = self.root / f"{artifact_id}.{suffix}"
        if not path.is_file():
            raise FileNotFoundError(f"Artifact does not exist: {artifact_id}")
        return path.read_bytes()


def _depth_mean_percent(layers: list[np.ma.MaskedArray]) -> np.ma.MaskedArray:
    if len(layers) != 3:
        raise ValueError("All three SoilGrids depth intervals are required")
    stack = np.ma.stack(layers).astype(float)
    missing = np.ma.getmaskarray(stack).any(axis=0)
    result = (stack.filled(0) * np.array([5, 10, 15])[:, None, None]).sum(axis=0) / 3000
    return np.ma.array(result, mask=missing)


def _json_grid(values: np.ma.MaskedArray) -> list[list[float | None]]:
    mask = np.ma.getmaskarray(values)
    return [
        [None if mask[row, column] else float(values.data[row, column]) for column in range(values.shape[1])]
        for row in range(values.shape[0])
    ]


def _hex_color(red: float, green: float, blue: float) -> str:
    return f"#{round(red):02X}{round(green):02X}{round(blue):02X}"


def _legend(minimum: float, maximum: float) -> tuple[LegendEntry, ...]:
    if maximum == minimum:
        return (LegendEntry(value=minimum, color=LEGEND_COLORS[1]),)
    return (
        LegendEntry(value=minimum, color=LEGEND_COLORS[0]),
        LegendEntry(value=(minimum + maximum) / 2, color=LEGEND_COLORS[1]),
        LegendEntry(value=maximum, color=LEGEND_COLORS[2]),
    )


def _render_png(values: np.ma.MaskedArray, minimum: float, maximum: float) -> bytes:
    normalized = np.zeros(values.shape, dtype=float)
    if maximum > minimum:
        normalized = (values.filled(minimum) - minimum) / (maximum - minimum)
    normalized = np.clip(normalized, 0, 1)
    red = np.where(normalized < 0.5, 33 + normalized * 2 * (247 - 33), 247 + (normalized - 0.5) * 2 * (178 - 247))
    green = np.where(normalized < 0.5, 102 + normalized * 2 * (247 - 102), 247 + (normalized - 0.5) * 2 * (24 - 247))
    blue = np.where(normalized < 0.5, 172 + normalized * 2 * (247 - 172), 247 + (normalized - 0.5) * 2 * (43 - 247))
    rgba = np.stack([red, green, blue, np.where(np.ma.getmaskarray(values), 0, 255)], axis=0).astype("uint8")
    with MemoryFile() as memory_file:
        with memory_file.open(
            driver="PNG",
            width=values.shape[1],
            height=values.shape[0],
            count=4,
            dtype="uint8",
        ) as dataset:
            dataset.write(rgba)
        return memory_file.read()


class SoilLayerService:
    """Synchronous M1 service call; callers may run it in a worker thread."""

    def __init__(self, adapter: SoilGridsAdapter, artifact_store: ArtifactStore) -> None:
        self.adapter = adapter
        self.artifact_store = artifact_store

    def create_layer(self, request: LayerRequest) -> LayerResult:
        field_id = request.fields.features[0].id
        try:
            rasters, provenance = self.adapter.retrieve(request)
            values = _depth_mean_percent([raster.values for raster in rasters])
            if values.count() == 0:
                return LayerResult(
                    status=ResultStatus.NO_DATA,
                    error=LayerError(
                        code="no_data",
                        message="No complete clay profile intersects the field",
                    ),
                )
            if values.min() < 0 or values.max() > 100:
                raise ValueError("Normalized clay percentage is outside the physical range")
            minimum, mean, maximum = (
                float(values.min()),
                float(values.mean()),
                float(values.max()),
            )
            legend = _legend(minimum, maximum)
            first_raster = rasters[0]
            json_payload = json.dumps(
                {
                    "fieldId": field_id,
                    "parameter": "clay",
                    "source": "soilgrids",
                    "unit": "percent",
                    "depth": {"topCm": 0, "bottomCm": 30},
                    "grid": {
                        "values": _json_grid(values),
                        "crs": first_raster.crs.to_string(),
                        "width": values.shape[1],
                        "height": values.shape[0],
                        "transform": list(first_raster.transform)[:6],
                        "rowOrder": "northToSouth",
                        "columnOrder": "westToEast",
                    },
                    "legend": [entry.model_dump() for entry in legend],
                    "statistics": {
                        "validPixelCount": int(values.count()),
                        "minimum": minimum,
                        "mean": mean,
                        "maximum": maximum,
                    },
                },
                indent=2,
                allow_nan=False,
            ).encode()
            png_payload = _render_png(values, minimum, maximum)
            json_id = self.artifact_store.put("json", json_payload)
            png_id = self.artifact_store.put("png", png_payload)
            grid_bounds = rasterio.transform.array_bounds(
                values.shape[0], values.shape[1], first_raster.transform
            )
            west, south, east, north = (
                grid_bounds[0],
                grid_bounds[1],
                grid_bounds[2],
                grid_bounds[3],
            )
            data = LayerData(
                field_id=field_id,
                parameter="clay",
                source="soilgrids",
                unit="percent",
                depth=request.depth,
                grid={
                    "crs": first_raster.crs.to_string(),
                    "width": values.shape[1],
                    "height": values.shape[0],
                    "transform": tuple(first_raster.transform)[:6],
                    "bounds": {
                        "west": west,
                        "south": south,
                        "east": east,
                        "north": north,
                    },
                },
                statistics=LayerStatistics(
                    valid_pixel_count=int(values.count()),
                    minimum=minimum,
                    mean=mean,
                    maximum=maximum,
                ),
                artifacts=(
                    ArtifactReference(
                        artifact_id=png_id, kind=ArtifactKind.PNG, media_type="image/png"
                    ),
                    ArtifactReference(
                        artifact_id=json_id,
                        kind=ArtifactKind.JSON_GRID,
                        media_type="application/json",
                    ),
                ),
                retrieved_at=str(provenance["retrieved_at"]),
                dataset_version=provenance["dataset_version"],
                dataset_date=provenance["dataset_date"],
                method=CLAY_METHOD,
                legend=legend,
                provenance=provenance,
            )
            return LayerResult(status=ResultStatus.AVAILABLE, data=data)
        except SoilGridsProviderTimeout as error:
            return LayerResult(
                status=ResultStatus.FAILED,
                error=LayerError(
                    code="provider_timeout", message=str(error), retryable=True
                ),
            )
        except SoilGridsProviderError as error:
            return LayerResult(
                status=ResultStatus.FAILED,
                error=LayerError(
                    code="provider_failure", message=str(error), retryable=True
                ),
            )
        except (OSError, ValueError) as error:
            return LayerResult(
                status=ResultStatus.FAILED,
                error=LayerError(code="processing_failure", message=str(error)),
            )
