"""Deterministic checks; these do not demonstrate provider availability."""

import unittest
import numpy as np
from rasterio.features import geometry_mask
from rasterio.transform import from_origin

from scripts.soilgrids_0a import depth_mean_percent, json_grid


class DepthChecks(unittest.TestCase):
    def test_independent_depth_example_and_missing_interval(self):
        # (100*5 + 200*10 + 300*15)/30 = 233 1/3 g/kg = 23 1/3 percent.
        layers = [np.ma.array([[value, value]], mask=[[False, missing]])
                  for value, missing in [(100, False), (200, True), (300, False)]]
        result = depth_mean_percent(layers)
        self.assertAlmostEqual(result[0, 0], 70 / 3)
        self.assertEqual(json_grid(result), [[result[0, 0], None]])

    def test_zero_is_valid_and_depths_are_required(self):
        result = depth_mean_percent([np.ma.array([[0]]) for _ in range(3)])
        self.assertEqual(json_grid(result), [[0.0]])
        with self.assertRaises(ValueError):
            depth_mean_percent([np.ma.array([[100]])])

    def test_polygon_hole_and_exterior_mask(self):
        polygon = {"type": "Polygon", "coordinates": [
            [[0, 0], [3, 0], [3, 3], [0, 3], [0, 0]],
            [[1, 1], [1, 2], [2, 2], [2, 1], [1, 1]],
        ]}
        mask = geometry_mask([polygon], (3, 4), from_origin(0, 3, 1, 1), all_touched=False)
        np.testing.assert_array_equal(mask, [
            [False, False, False, True], [False, True, False, True],
            [False, False, False, True],
        ])


if __name__ == "__main__":
    unittest.main()
