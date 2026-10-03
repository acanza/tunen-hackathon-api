"""Yield potential v1: water-scaled multi-year relative NDVI, blended with a soil/terrain model.

All quantities are relative within a field (field mean ≈ 1), because absolute NDVI differs by crop
and year and there is no harvest data. The final index is rescaled per field to mean = 100.

1. Per-season relative peak NDVI (same rules as data/seggerde/sentinel2/field_stats.py).
2. Per pixel: level (mean relative NDVI) and its sensitivity to the Apr–Jun climatic water balance,
   shrunk toward the field median; evaluated for a normal / dry / wet spring (1991–2020 ERA5-Land).
3. Soil/terrain model (ridge) predicting the level from field-centred covariates (grouped CV by field).
4. Blend by NDVI reliability (empirical-Bayes per field, see ndvi_weight); w = 0 where there is no NDVI.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.features import rasterize
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import GroupKFold

# rules ported from field_stats.py
MIN_PEAK_OBS = 2
MIN_SEASON_PEAK = 0.40
MIN_SEASONS = 3
ZONE_INNER_M = 10
MIN_ZONE_PX = 20
SD_FLOOR = 0.02

SLOPE_SHRINK_K = 4          # slope weight n / (n + k): with n ≤ 8 seasons the per-pixel slope is noisy
CLIMATE_YEARS = (1991, 2020)
SCENARIO_QUANTILES = {"dry": 0.2, "wet": 0.8}


@dataclass
class Seasons:
    years: list[int]
    rel: np.ndarray        # (S, H, W) pixel peak / field inner-10 m mean; NaN where unused
    z: np.ndarray          # (S, H, W) within-field z-score
    fid: np.ndarray        # (H, W) field index (1..n) on inner-10 m pixels, 0 elsewhere
    plot_ids: list[str]    # plot_ids[k-1] ↔ fid == k


def season_rel(fields_utm, peaks_dir: Path, transform, shape) -> Seasons:
    """`fields_utm`: GeoDataFrame in the grid CRS with plotId, use_for_stats."""
    gs = fields_utm[fields_utm.use_for_stats.astype(bool)].reset_index(drop=True)
    ids = np.arange(1, len(gs) + 1)
    order = gs.geometry.area.sort_values(ascending=False).index   # smaller fields drawn last
    inner = gs.geometry.buffer(-ZONE_INNER_M)
    fid = rasterize([(inner[i], ids[i]) for i in order if not inner[i].is_empty],
                    out_shape=shape, transform=transform, fill=0, dtype="int32")
    for k in ids:
        if (fid == k).sum() < MIN_ZONE_PX:
            fid[fid == k] = 0
    years, rels, zs = [], [], []
    for p in sorted(peaks_dir.glob("ndvi_peak_*.tif")):
        with rasterio.open(p) as r:
            p90, nobs = r.read(1), r.read(3)
        p90 = np.where(nobs >= MIN_PEAK_OBS, p90, np.nan)
        rel = np.full(shape, np.nan, np.float32)
        z = np.full(shape, np.nan, np.float32)
        for k in ids:
            sel = fid == k
            inn = sel & np.isfinite(p90)
            if not sel.any() or inn.sum() < max(3, 0.5 * sel.sum()):
                continue
            v = p90[inn]
            mu, sd = float(v.mean()), float(v.std())
            if mu < MIN_SEASON_PEAK:
                continue
            rel[sel] = p90[sel] / mu
            z[sel] = (p90[sel] - mu) / max(sd, SD_FLOOR)
        years.append(int(p.stem.split("_")[-1])); rels.append(rel); zs.append(z)
    return Seasons(years, np.stack(rels), np.stack(zs), fid, gs.plotId.tolist())


def cwb_apr_jun(daily_csv: Path, cells_csv: Path) -> pd.Series:
    """Farm Apr–Jun climatic water balance (precipitation − ET₀, mm) per year, area-weighted over cells."""
    d = pd.read_csv(daily_csv, usecols=["cell", "date", "precipitation_sum", "et0_fao_evapotranspiration"],
                    parse_dates=["date"])
    d = d[d.date.dt.month.isin([4, 5, 6])]
    d["cwb"] = d.precipitation_sum - d.et0_fao_evapotranspiration
    per = d.groupby(["cell", d.date.dt.year]).agg(cwb=("cwb", "sum"), n=("cwb", "size"))
    per = per[per.n >= 85].cwb.unstack(0)                     # complete Apr–Jun only (91 days)
    w = pd.read_csv(cells_csv).set_index("cell").area_ha
    return (per[w.index] * w).sum(1) / w.sum()


def scenarios(cwb: pd.Series) -> dict[str, float]:
    clim = cwb.loc[CLIMATE_YEARS[0]:CLIMATE_YEARS[1]]
    out = {"normal": float(clim.mean())}
    out |= {k: float(clim.quantile(q)) for k, q in SCENARIO_QUANTILES.items()}
    return out


@dataclass
class NdviComponent:
    level: np.ndarray       # mean relative NDVI over used seasons
    slope: np.ndarray       # shrunk d(rel)/d(cwb) per mm
    xbar: np.ndarray        # mean CWB of the pixel's used seasons
    n: np.ndarray           # seasons used
    sd_rel: np.ndarray
    sd_z: np.ndarray

    def at(self, cwb_value: float) -> np.ndarray:
        return self.level + self.slope * (cwb_value - self.xbar)


def ndvi_component(s: Seasons, cwb: pd.Series, use: list[int] | None = None) -> NdviComponent:
    """Per-pixel level and water sensitivity from the seasons in `use` (all by default)."""
    idx = [i for i, y in enumerate(s.years) if use is None or y in use]
    R, Z = s.rel[idx], s.z[idx]
    x = np.array([cwb[s.years[i]] for i in idx], "float64")[:, None, None]
    m = np.isfinite(R)
    n = m.sum(0)
    ok = n >= MIN_SEASONS
    xm = np.where(m, x, np.nan)
    xbar = np.nanmean(xm, 0)
    level = np.nanmean(R, 0)
    dx = xm - xbar
    sxx = np.nansum(dx ** 2, 0)
    slope = np.where(sxx > 0, np.nansum(dx * (R - level), 0) / np.where(sxx > 0, sxx, 1), 0.0)
    # shrink toward the field median slope
    fmed = np.zeros_like(slope)
    for k in np.unique(s.fid[s.fid > 0]):
        sel = (s.fid == k) & ok
        if sel.any():
            fmed[s.fid == k] = np.median(slope[sel])
    wn = n / (n + SLOPE_SHRINK_K)
    slope = wn * slope + (1 - wn) * fmed
    nan = np.where(ok, 1.0, np.nan)
    return NdviComponent((level * nan).astype("float32"), (slope * nan).astype("float32"),
                         (xbar * nan).astype("float32"), n.astype("float32"),
                         (np.nanstd(R, 0) * nan).astype("float32"), (np.nanstd(Z, 0) * nan).astype("float32"))


def field_index(fields_utm, transform, shape) -> tuple[np.ndarray, list[str]]:
    """All-fields index raster (all-touched; smaller fields win), for centring covariates per field."""
    g = fields_utm.reset_index(drop=True)
    ids = np.arange(1, len(g) + 1)
    order = g.geometry.area.sort_values(ascending=False).index
    fall = rasterize([(g.geometry[i], ids[i]) for i in order], out_shape=shape, transform=transform,
                     fill=0, dtype="int32", all_touched=True)
    return fall, g.plotId.tolist()


def centre_by_field(a: np.ndarray, fall: np.ndarray) -> np.ndarray:
    out = np.full(a.shape, np.nan, "float32")
    for k in np.unique(fall[fall > 0]):
        sel = fall == k
        v = a[sel]
        if np.isfinite(v).any():
            out[sel] = v - np.nanmean(v)
    return out


@dataclass
class SoilModel:
    pred: np.ndarray        # predicted relative level (1 = field mean) on all field pixels
    resid_sd: float         # out-of-fold residual SD
    r2_oof: float
    n_train: int
    features: list[str]
    coef: dict[str, float]


def soil_model(covariates: dict[str, np.ndarray], target: np.ndarray, fall: np.ndarray,
               train_groups: np.ndarray) -> SoilModel:
    """Ridge on field-centred covariates; target = level − field mean.

    Across fields these covariates explain almost none of the within-field NDVI pattern (the sign of
    the terrain effect flips between wet and dry soils), so a strongly regularised linear model is
    used: it stays close to the field mean instead of inventing patterns where NDVI is missing.
    """
    names = list(covariates)
    X = np.stack([np.nan_to_num(centre_by_field(v, fall)) for v in covariates.values()], -1)
    sd = X[fall > 0].std(0)
    X = X / np.where(sd > 0, sd, 1)
    yc = centre_by_field(target, train_groups)
    tr = (train_groups > 0) & np.isfinite(yc)
    Xt, yt, gt = X[tr], yc[tr], train_groups[tr]
    alphas = np.logspace(0, 6, 13)
    oof = np.full(yt.shape, np.nan)
    for a, b in GroupKFold(n_splits=5).split(Xt, yt, gt):
        oof[b] = RidgeCV(alphas=alphas, fit_intercept=False).fit(Xt[a], yt[a]).predict(Xt[b])
    resid = yt - oof
    full = RidgeCV(alphas=alphas, fit_intercept=False).fit(Xt, yt)
    pred = np.full(fall.shape, np.nan, "float32")
    pred[fall > 0] = 1 + full.predict(X[fall > 0])
    return SoilModel(pred, float(np.std(resid)), float(1 - np.var(resid) / np.var(yt)), int(tr.sum()), names,
                     {n: round(float(c), 5) for n, c in zip(names, full.coef_)})


def ndvi_weight(nd: NdviComponent, fid: np.ndarray) -> np.ndarray:
    """Empirical-Bayes reliability of each pixel's NDVI level, per field.

    Within a field, the spread of pixel levels = stable pattern (signal) + year-to-year noise / n.
    w = signal / (signal + sd_rel² / n): stable, many-season pixels keep their NDVI value; noisy ones
    are pulled toward the soil/terrain prediction. w = 0 where there is no NDVI.
    """
    w = np.zeros(fid.shape, "float32")
    ok = np.isfinite(nd.level) & np.isfinite(nd.sd_rel) & (nd.n > 0)
    for k in np.unique(fid[fid > 0]):
        sel = (fid == k) & ok
        if sel.sum() < 2:
            continue
        noise = nd.sd_rel[sel] ** 2 / nd.n[sel]
        signal = max(float(np.var(nd.level[sel]) - noise.mean()), 0.0)
        w[sel] = signal / (signal + noise) if signal > 0 else 0.0
    return w


def blend(nd: NdviComponent, yp_ndvi: np.ndarray, soil: SoilModel, fid: np.ndarray):
    """Returns (yp, sigma, w).

    sigma is the uncertainty of the long-term potential, not of a single season: the NDVI part uses the
    standard error of the multi-year mean (sd_rel / √n). Year-to-year instability is flagged separately
    (unstable pixels → low confidence). With the soil/terrain prediction as the prior, the shrinkage
    posterior variance is w·se²; pixels without NDVI carry the soil model's residual variance.
    """
    has = np.isfinite(yp_ndvi)
    w = np.where(has, ndvi_weight(nd, fid), 0.0)
    ndvi = np.where(has, yp_ndvi, 0.0)
    se2 = np.where(has, np.nan_to_num(nd.sd_rel) ** 2 / np.maximum(nd.n, 1), 0.0)
    yp = w * ndvi + (1 - w) * soil.pred
    var = np.where(w > 0, w * se2, soil.resid_sd ** 2)
    yp = np.where(np.isfinite(soil.pred), yp, np.nan)
    return yp.astype("float32"), np.sqrt(var).astype("float32"), w.astype("float32")
