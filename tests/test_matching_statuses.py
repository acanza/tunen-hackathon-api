"""Regression tests for matching and layer status behavior."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import unittest

from fastapi.testclient import TestClient

from soil_api.app import app


REQUEST_PATH = Path(__file__).resolve().parents[1] / "docs" / "poc" / "samples" / "request.json"
DATABASE_PATH = REQUEST_PATH.parents[1] / "store" / "soil.sqlite"


class MatchingStatusRegressionTest(unittest.TestCase):
    """Keep the documented west/east/sliver/outside outcomes stable."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)
        request_body = json.loads(REQUEST_PATH.read_text())
        response = cls.client.post("/soil/layers", json=request_body)
        if response.status_code != 200:
            raise AssertionError(response.text)
        cls.fields = {field["id"]: field for field in response.json()["fields"]}

    @staticmethod
    def _layer(field: dict, parameter: str, source: str) -> dict:
        return next(
            layer
            for layer in field["layers"]
            if layer["parameter"] == parameter and layer["source"] == source
        )

    def test_every_field_contains_the_complete_requested_matrix(self) -> None:
        expected_pairs = {
            (parameter, source)
            for parameter in (
                "texture",
                "ph",
                "soc",
                "nfk",
                "bodenzahl",
                "yield_potential",
            )
            for source in (
                "soilgrids",
                "lbeg_bk50",
                "lbeg_bodenschaetzung",
                "derived",
            )
        }
        for field in self.fields.values():
            pairs = {(layer["parameter"], layer["source"]) for layer in field["layers"]}
            self.assertEqual(pairs, expected_pairs)
            self.assertEqual(len(pairs), len(field["layers"]))

    def test_western_field_preserves_lbeg_data(self) -> None:
        layer = self._layer(self.fields["f1"], "bodenzahl", "lbeg_bodenschaetzung")

        self.assertEqual(self.fields["f1"]["match"], "plot_id")
        self.assertIn(layer["status"], {"ok", "partial"})
        self.assertIsNone(layer.get("reason"))
        self.assertIn("stats", layer)
        self.assertIn("png_url", layer)

    def test_eastern_field_reports_missing_lbeg_coverage(self) -> None:
        layer = self._layer(self.fields["f2"], "bodenzahl", "lbeg_bodenschaetzung")

        self.assertEqual(layer["status"], "unavailable")
        self.assertEqual(layer["reason"], "outside_source_region:niedersachsen")
        self.assertEqual(layer["coverage"], 0.0)
        self.assertEqual(layer["unit"], "points")
        self.assertNotIn("stats", layer)
        self.assertNotIn("png_url", layer)

    def test_sliver_reports_unavailable_yield_and_fallback_stats(self) -> None:
        yield_layer = self._layer(self.fields["f3"], "yield_potential", "derived")
        texture_layer = self._layer(self.fields["f3"], "texture", "soilgrids")

        self.assertEqual(
            yield_layer["reason"],
            "field_excluded_from_ndvi_stats:sliver_or_overlap",
        )
        self.assertEqual(yield_layer["status"], "unavailable")
        self.assertEqual(texture_layer["stats"]["zone"], "full_field_fallback")

    def test_outside_polygon_has_explicit_unavailable_layers(self) -> None:
        field = self.fields["f4"]

        self.assertEqual(field["match"], "outside_coverage_area")
        self.assertIsNone(field["bounds"])
        for layer in field["layers"]:
            if layer["status"] == "not_applicable":
                self.assertEqual(layer["reason"], "source_does_not_provide_parameter")
            else:
                self.assertEqual(layer["status"], "unavailable")
                self.assertEqual(layer["reason"], "outside_coverage_area")
                self.assertNotIn("stats", layer)
                self.assertNotIn("png_url", layer)

    def test_partial_layers_remain_explicit(self) -> None:
        with sqlite3.connect(DATABASE_PATH) as connection:
            plot_id, geometry_json, parameter, source = connection.execute(
                """
                SELECT fields.plot_id, fields.geom_geojson,
                       field_layers.parameter, field_layers.source
                FROM fields
                JOIN field_layers ON field_layers.plot_id = fields.plot_id
                WHERE field_layers.status = 'partial'
                ORDER BY fields.plot_id, field_layers.parameter, field_layers.source
                LIMIT 1
                """
            ).fetchone()
        request_body = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "partial-field",
                    "properties": {"plotId": plot_id},
                    "geometry": json.loads(geometry_json),
                }
            ],
            "parameters": [parameter],
            "sources": [source],
        }
        response = self.client.post("/soil/layers", json=request_body)
        self.assertEqual(response.status_code, 200)
        layer = response.json()["fields"][0]["layers"][0]
        self.assertEqual(layer["status"], "partial")
