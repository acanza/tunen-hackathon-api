"""Terrain covariates on the Sentinel-2 10 m grid from the Copernicus GLO-30 window on disk.

The DEM is a surface model: forest canopy (~20 m) and hedges sit on top of the ground. Only pixels
inside the farm's fields (10 m in from the edge) are trusted as bare ground; everything else is
replaced by a ground surface interpolated from them (multi-scale normalised convolution), then the
whole surface is lightly smoothed before any derivative.
Flow routing is plain numpy/heapq (priority-flood fill + D8), which is fast enough for the
farm grid (~650k cells) and avoids compiled GIS dependencies.
"""
from __future__ import annotations

import heapq
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject
from scipy.ndimage import gaussian_filter, uniform_filter

CELL_M = 10.0
SMOOTH_SIGMA_PX = 2.5      # ~25 m SD, ~50 m effective width: removes small bumps left in fields
INTERP_SIGMAS_PX = (3, 10, 30, 100)  # 30 m → 1 km: gaps filled from the nearest scale with enough ground
REL_ELEV_WINDOW_PX = 21    # ~210 m box: field-scale knolls and hollows (strongest NDVI signal)
MIN_TAN_SLOPE = 0.001      # flat-ground floor for TWI

# D8 neighbour offsets and their distances in cells
D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
D8_DIST = np.array([np.hypot(dr, dc) for dr, dc in D8])


def to_grid(path: Path, transform, height: int, width: int, crs: str) -> np.ndarray:
    dst = np.full((height, width), np.nan, "float32")
    with rasterio.open(path) as src:
        reproject(rasterio.band(src, 1), dst, dst_transform=transform, dst_crs=crs,
                  resampling=Resampling.bilinear, dst_nodata=np.nan)
    return dst


def priority_flood(z: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    """Fill depressions so every cell drains to the grid edge (Barnes et al. 2014, epsilon variant)."""
    h, w = z.shape
    filled = z.astype("float64").copy()
    done = np.zeros(z.shape, bool)
    heap: list[tuple[float, int, int]] = []
    for r in range(h):
        for c in (0, w - 1):
            heap.append((filled[r, c], r, c)); done[r, c] = True
    for c in range(1, w - 1):
        for r in (0, h - 1):
            heap.append((filled[r, c], r, c)); done[r, c] = True
    heapq.heapify(heap)
    while heap:
        e, r, c = heapq.heappop(heap)
        for dr, dc in D8:
            rr, cc = r + dr, c + dc
            if 0 <= rr < h and 0 <= cc < w and not done[rr, cc]:
                done[rr, cc] = True
                if filled[rr, cc] <= e:
                    filled[rr, cc] = e + eps
                heapq.heappush(heap, (filled[rr, cc], rr, cc))
    return filled


def d8_accumulation(filled: np.ndarray) -> np.ndarray:
    """Upslope cell count (incl. the cell itself) with steepest-descent D8 routing."""
    h, w = filled.shape
    pad = np.pad(filled, 1, constant_values=np.inf)
    drops = np.stack([(filled - pad[1 + dr:1 + dr + h, 1 + dc:1 + dc + w]) / d
                      for (dr, dc), d in zip(D8, D8_DIST)])
    best = drops.argmax(0)
    has_out = drops.max(0) > 0
    idx = np.arange(h * w).reshape(h, w)
    dr = np.array([o[0] for o in D8])[best]
    dc = np.array([o[1] for o in D8])[best]
    rr, cc = np.clip(idx // w + dr, 0, h - 1), np.clip(idx % w + dc, 0, w - 1)
    receiver = np.where(has_out, rr * w + cc, -1).ravel()
    acc = np.ones(h * w)
    for i in np.argsort(-filled.ravel(), kind="stable"):   # high to low
        j = receiver[i]
        if j >= 0:
            acc[j] += acc[i]
    return acc.reshape(h, w)


def ground_surface(raw: np.ndarray, ground: np.ndarray) -> np.ndarray:
    """Keep trusted ground pixels; fill the rest by normalised convolution, blending scales smoothly.

    Each scale's estimate is trusted in proportion to how much ground supports it there, and the
    remainder comes from the next coarser scale, so there are no seams between scales.
    """
    m = (ground & np.isfinite(raw)).astype("float64")
    z = np.where(m > 0, raw, 0.0)
    out = np.full(raw.shape, np.nanmean(raw[m > 0]) if m.any() else np.nanmean(raw))
    for sigma in reversed(INTERP_SIGMAS_PX):            # coarse → fine
        w = gaussian_filter(m, sigma, mode="nearest")
        est = gaussian_filter(z, sigma, mode="nearest") / np.maximum(w, 1e-12)
        a = np.clip(w / 0.25, 0, 1)                     # full trust once a quarter of the kernel is ground
        out = a * est + (1 - a) * out
    return out   # also used on ground pixels (30 m-smoothed there), so field edges have no step


def terrain(dem_path: Path, transform, height: int, width: int, crs: str,
            ground: np.ndarray) -> dict[str, np.ndarray]:
    raw = to_grid(dem_path, transform, height, width, crs)
    nan = ~np.isfinite(raw)
    zs = gaussian_filter(ground_surface(raw, ground), SMOOTH_SIGMA_PX)

    gy, gx = np.gradient(zs, CELL_M)
    tan_b = np.hypot(gx, gy)
    slope = np.degrees(np.arctan(tan_b))

    acc = d8_accumulation(priority_flood(zs))
    sca = acc * CELL_M * CELL_M / CELL_M   # specific catchment area: upslope area per unit contour width
    twi = np.log(sca / np.maximum(tan_b, MIN_TAN_SLOPE))

    rel = zs - uniform_filter(zs, REL_ELEV_WINDOW_PX, mode="nearest")
    out = {"elev": zs, "slope": slope, "twi": twi, "rel_elev": rel,
           "ground_mask": ground.astype("float32")}
    for k in out:
        out[k] = np.where(nan, np.nan, out[k]).astype("float32")
    return out
