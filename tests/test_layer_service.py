import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.transform import from_origin

from soil_api.domain import (
    GeoJsonFeature,
    GeoJsonFeatureCollection,
    GeoJsonPolygon,
    LayerRequest,
    ResultStatus,
)
from soil_api.layer_service import ArtifactStore, SoilLayerService
from soil_api.providers.soilgrids import (
    SoilGridsProviderTimeout,
    SoilGridsRaster,
)


def request() -> LayerRequest:
    geometry = GeoJsonPolygon(
        type="Polygon",
        coordinates=[
            [
                (0, 0),
                (0.004, 0),
                (0.004, 0.003),
                (0, 0.003),
                (0, 0),
            ]
        ],
    )
    return LayerRequest(
        fields=GeoJsonFeatureCollection(
            type="FeatureCollection",
            features=[GeoJsonFeature(type="Feature", id="field-1", geometry=geometry)],
        )
    )


class FakeAdapter:
    def __init__(self, layers):
        self.layers = layers

    def retrieve(self, _request):
        return self.layers, {
            "retrieved_at": "2026-10-03T12:00:00+00:00",
            "dataset_version": "fixture",
            "dataset_date": None,
            "source_url": "fixture://soilgrids",
            "source_crs": "EPSG:4326",
            "source_resolution_meters": 1,
            "original_unit": "g/kg",
            "depth_intervals_cm": [[0, 5], [5, 15], [15, 30]],
            "metadata": [],
        }


def fixture_rasters(all_masked=False):
    transform = from_origin(0, 3, 1, 1)
    rasters = []
    for index, values in enumerate(
        (
            [[100, 200, 300, 400], [100, 200, 300, 400], [100, 200, 300, 400]],
            [[100, 200, 300, 400], [100, 200, 300, 400], [100, 200, 300, 400]],
            [[100, 200, 300, 400], [100, 200, 300, 400], [100, 200, 300, 400]],
        )
    ):
        data = np.ma.array(values, mask=all_masked)
        rasters.append(
            SoilGridsRaster(
                coverage_id=f"depth-{index}",
                values=data,
                transform=transform,
                crs=CRS.from_epsg(4326),
                nodata=-32768,
                metadata={},
            )
        )
    return rasters


class LayerServiceChecks(unittest.TestCase):
    def test_generates_retrievable_json_and_transparent_png(self):
        with tempfile.TemporaryDirectory() as directory:
            service = SoilLayerService(
                FakeAdapter(fixture_rasters()),
                ArtifactStore(Path(directory)),
            )
            result = service.create_layer(request())

            self.assertEqual(result.status, ResultStatus.AVAILABLE)
            self.assertIsNotNone(result.data)
            self.assertEqual(result.data.statistics.valid_pixel_count, 12)
            self.assertAlmostEqual(result.data.statistics.minimum, 1)
            self.assertAlmostEqual(result.data.statistics.maximum, 4)
            artifacts = {artifact.kind: artifact for artifact in result.data.artifacts}
            grid = json.loads(
                service.artifact_store.get(
                    artifacts[next(kind for kind in artifacts if kind.value == "json_grid")].artifact_id,
                    next(kind for kind in artifacts if kind.value == "json_grid"),
                )
            )
            self.assertEqual(grid["grid"]["values"][0][0], 1.0)
            self.assertEqual(grid["grid"]["rowOrder"], "northToSouth")
            png = service.artifact_store.get(
                artifacts[next(kind for kind in artifacts if kind.value == "png")].artifact_id,
                next(kind for kind in artifacts if kind.value == "png"),
            )
            self.assertTrue(png.startswith(b"\x89PNG"))

    def test_nodata_is_null_and_png_alpha_is_transparent(self):
        rasters = fixture_rasters()
        for raster in rasters:
            raster.values.mask[1, 1] = True
        with tempfile.TemporaryDirectory() as directory:
            service = SoilLayerService(FakeAdapter(rasters), ArtifactStore(Path(directory)))
            result = service.create_layer(request())
            self.assertEqual(result.data.statistics.valid_pixel_count, 11)
            artifacts = {artifact.kind.value: artifact for artifact in result.data.artifacts}
            grid = json.loads(
                service.artifact_store.get(
                    artifacts["json_grid"].artifact_id, artifacts["json_grid"].kind
                )
            )
            self.assertIsNone(grid["grid"]["values"][1][1])
            with MemoryFile(
                service.artifact_store.get(
                    artifacts["png"].artifact_id, artifacts["png"].kind
                )
            ) as memory_file:
                with memory_file.open() as dataset:
                    self.assertEqual(dataset.read(4)[1, 1], 0)

    def test_all_nodata_is_not_empty_success(self):
        with tempfile.TemporaryDirectory() as directory:
            service = SoilLayerService(
                FakeAdapter(fixture_rasters(all_masked=True)),
                ArtifactStore(Path(directory)),
            )
            result = service.create_layer(request())
            self.assertEqual(result.status, ResultStatus.NO_DATA)
            self.assertEqual(result.error.code.value, "no_data")

    def test_timeout_is_explicit_failure(self):
        class TimeoutAdapter:
            def retrieve(self, _request):
                raise SoilGridsProviderTimeout("timed out")

        with tempfile.TemporaryDirectory() as directory:
            result = SoilLayerService(
                TimeoutAdapter(), ArtifactStore(Path(directory))
            ).create_layer(request())
            self.assertEqual(result.status, ResultStatus.FAILED)
            self.assertEqual(result.error.code.value, "provider_timeout")


if __name__ == "__main__":
    unittest.main()
