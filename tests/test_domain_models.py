"""Deterministic closure checks for implementation unit 1A."""

import math
import unittest

from pydantic import ValidationError

from soil_api.domain import (
    CoordinateBounds,
    ErrorCode,
    GeoJsonFeature,
    GeoJsonFeatureCollection,
    GeoJsonMultiPolygon,
    GeoJsonPolygon,
    LayerError,
    LayerRequest,
    LayerResult,
    ResultStatus,
)


def polygon(coordinates):
    return GeoJsonPolygon(type="Polygon", coordinates=[coordinates])


def feature(field_id="field-1", geometry=None):
    return GeoJsonFeature(
        type="Feature",
        id=field_id,
        geometry=geometry
        or polygon(
            [
                (11.045702, 52.344595),
                (11.054692, 52.344595),
                (11.054692, 52.348776),
                (11.045702, 52.348776),
                (11.045702, 52.344595),
            ]
        ),
    )


def request_for(*features):
    return LayerRequest(
        fields=GeoJsonFeatureCollection(type="FeatureCollection", features=list(features))
    )


class RequestValidationChecks(unittest.TestCase):
    def test_accepts_one_valid_polygon_and_fixed_contract(self):
        request = request_for(feature())
        self.assertEqual(request.fields.features[0].id, "field-1")
        self.assertEqual(request.depth.top_cm, 0)
        self.assertEqual(request.depth.bottom_cm, 30)

    def test_accepts_multipolygon(self):
        geometry = GeoJsonMultiPolygon(
            type="MultiPolygon",
            coordinates=[
                [[(11, 52), (11.001, 52), (11.001, 52.001), (11, 52)]],
                [[(11.002, 52), (11.003, 52), (11.003, 52.001), (11.002, 52)]],
            ],
        )
        self.assertEqual(request_for(feature(geometry=geometry)).fields.features[0].geometry.type, "MultiPolygon")

    def test_accepts_two_fields_and_rejects_three(self):
        self.assertEqual(len(request_for(feature("field-1"), feature("field-2")).fields.features), 2)
        with self.assertRaisesRegex(ValidationError, "maximum is 2"):
            request_for(feature("field-1"), feature("field-2"), feature("field-3"))

    def test_rejects_absent_invalid_and_duplicate_identifier_cases(self):
        with self.assertRaises(ValidationError):
            GeoJsonFeature(type="Feature", geometry=feature().geometry)
        with self.assertRaises(ValidationError):
            feature("bad id")
        with self.assertRaisesRegex(ValidationError, "exactly one field"):
            request_for(feature("same"), feature("same"))

    def test_rejects_invalid_coordinate_and_unclosed_ring(self):
        with self.assertRaisesRegex(ValidationError, "longitude/latitude"):
            request_for(feature(geometry=polygon([(181, 1), (2, 1), (2, 2), (181, 1)])))
        with self.assertRaisesRegex(ValidationError, "must be closed"):
            request_for(feature(geometry=polygon([(1, 1), (2, 1), (2, 2), (1, 2)])))

    def test_rejects_self_intersection(self):
        bow_tie = polygon([(11, 52), (12, 53), (12, 52), (11, 53), (11, 52)])
        with self.assertRaisesRegex(ValidationError, "invalid field geometry"):
            request_for(feature(geometry=bow_tie))

    def test_rejects_unsupported_parameter_and_source(self):
        with self.assertRaises(ValidationError):
            LayerRequest(
                fields=GeoJsonFeatureCollection(
                    type="FeatureCollection", features=[feature()]
                ),
                parameters=["ph"],
            )
        with self.assertRaises(ValidationError):
            LayerRequest(
                fields=GeoJsonFeatureCollection(
                    type="FeatureCollection", features=[feature()]
                ),
                sources=["lbeg_bk50"],
            )

    def test_rejects_area_before_downstream_work(self):
        oversized = polygon([(10, 50), (11, 50), (11, 51), (10, 51), (10, 50)])
        with self.assertRaisesRegex(ValidationError, "exceeds 1000"):
            request_for(feature(geometry=oversized))

    def test_accepts_vertex_limit_and_rejects_next_vertex(self):
        center_longitude, center_latitude = 11.0, 52.0
        boundary_positions = [
            (
                center_longitude + 0.001 * math.cos(index * 2 * math.pi / 4_999),
                center_latitude + 0.001 * math.sin(index * 2 * math.pi / 4_999),
            )
            for index in range(4_999)
        ]
        boundary_positions.append(boundary_positions[0])
        self.assertEqual(
            len(request_for(feature(geometry=polygon(boundary_positions))).fields.features[0].geometry.coordinates[0]),
            5_000,
        )

        above_limit_positions = boundary_positions[:-1] + [boundary_positions[-2], boundary_positions[0]]
        with self.assertRaisesRegex(ValidationError, "maximum is 5000"):
            request_for(feature(geometry=polygon(above_limit_positions)))

    def test_rejects_pixel_budget_independently_of_area_budget(self):
        narrow_field = polygon(
            [(10, 52), (20, 52), (20, 52.0001), (10, 52.0001), (10, 52)]
        )
        with self.assertRaisesRegex(ValidationError, "pixels; maximum is 4096"):
            request_for(feature(geometry=narrow_field))


class ResultContractChecks(unittest.TestCase):
    def test_bounds_order_is_unambiguous(self):
        bounds = CoordinateBounds(west=11, south=52, east=12, north=53)
        self.assertEqual(bounds.as_wsen(), (11, 52, 12, 53))
        with self.assertRaises(ValidationError):
            CoordinateBounds(west=12, south=52, east=11, north=53)

    def test_failure_requires_error_and_never_data(self):
        result = LayerResult(
            status=ResultStatus.OUTSIDE_COVERAGE,
            error=LayerError(
                code=ErrorCode.OUTSIDE_COVERAGE,
                message="The field is outside source coverage",
            ),
        )
        self.assertIsNone(result.data)
        with self.assertRaises(ValidationError):
            LayerResult(status=ResultStatus.FAILED)

    def test_empty_success_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "available result requires data"):
            LayerResult(status=ResultStatus.AVAILABLE)


if __name__ == "__main__":
    unittest.main()
