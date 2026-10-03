"""Soil layers derived from coarse sources on disk (BÜK200 points, profiles)."""
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

BUEK_MAX_DIST_M = 150.0   # the BÜK200 sample points sit on a 125 m grid inside the fields


def buek_unit_raster(points_csv: Path, transform, height: int, width: int, crs: str) -> np.ndarray:
    """BÜK200 legend unit (TKLE_NR) of the nearest sample point; NaN farther than 150 m from any point.

    The BÜK200 service withholds polygon geometry, so this nearest-point map is the best unit map
    we can build from the 591 points queried inside the fields.
    """
    p = pd.read_csv(points_csv)
    xy = gpd.GeoSeries.from_xy(p.lon, p.lat, crs="EPSG:4326").to_crs(crs)
    tree = cKDTree(np.c_[xy.x, xy.y])
    cols, rows = np.meshgrid(np.arange(width) + 0.5, np.arange(height) + 0.5)
    x = transform.c + cols * transform.a
    y = transform.f + rows * transform.e
    dist, idx = tree.query(np.c_[x.ravel(), y.ravel()])
    unit = p.TKLE_NR.to_numpy(float)[idx]
    unit[dist > BUEK_MAX_DIST_M] = np.nan
    return unit.reshape(height, width).astype("float32")
