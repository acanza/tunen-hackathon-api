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


# ---------------------------------------------------------------- nFK from BÜK200 profiles

AGRI_LANDUSE = ("Acker", "Wiesen", "Weiden", "Grünland", "landwirtschaft")


def parse_profiles(html_path: Path) -> list[dict]:
    """Profiles of one BÜK200 legend unit: area share, land use and horizons (depths in dm)."""
    import re
    tables = pd.read_html(html_path)
    profiles, cur = [], None
    for t in tables:
        if t.shape[1] == 1:
            head = str(t.columns[0]).replace("\xad", "")
            m = re.search(r"Flächenanteil:\s*([\d.]+)\s*%", head)
            if m:
                lu = re.search(r"Landnutzung:\s*(.*?)\s*\(", head)
                cur = dict(share=float(m.group(1)), landuse=lu.group(1) if lu else "", horizons=[])
                profiles.append(cur)
        elif t.shape[1] >= 19 and cur is not None and not cur["horizons"]:
            for row in t.itertuples(index=False):
                v = list(row)
                cur["horizons"].append(dict(symbol=str(v[2]), top=float(v[3]), bottom=float(v[4]),
                                            bodenart=None if pd.isna(v[10]) else str(v[10]),
                                            humus=None if pd.isna(v[11]) else str(v[11]),
                                            ld=None if pd.isna(v[14]) else str(v[14]),
                                            peat=not pd.isna(v[15]) or str(v[2]).startswith("H")))
    return profiles


def profile_nfkwe(horizons: list[dict]) -> tuple[float, float]:
    """nFKWe (mm) over the effective rooting depth, and that depth (dm).

    Rooting stops at the KA5 effective rooting depth for the topsoil texture, or at the top of a
    permanently reduced (Gr) groundwater horizon. Capillary rise is not included (as in BK50 nFKWe).
    """
    from lib import ka5
    mineral = [h for h in horizons if h["bottom"] > 0]
    if not mineral:
        return float("nan"), 0.0
    top = mineral[0]
    we = ka5.WE_DM[ka5.texture_group(top["bodenart"], top["peat"])]
    gr = [h["top"] for h in mineral if "Gr" in h["symbol"]]
    bottom = min([we] + gr + [max(h["bottom"] for h in mineral)])
    total = 0.0
    for h in mineral:
        thick = max(0.0, min(h["bottom"], bottom) - max(h["top"], 0.0))
        vol = ka5.nfk_vol(h["bodenart"], h["ld"], h["humus"], h["peat"])
        if thick > 0 and vol is not None:
            total += vol * thick          # vol % × dm = mm
    return total, bottom


def unit_nfk(profile_dir: Path) -> pd.DataFrame:
    """Area-weighted nFKWe per BÜK200 unit over its agricultural profiles (all profiles if none)."""
    rows = []
    for p in sorted(profile_dir.glob("profile_*.html")):
        unit = int(p.stem.split("_")[1])
        profs = parse_profiles(p)
        for pr in profs:
            pr["nfkwe"], pr["we_dm"] = profile_nfkwe(pr["horizons"])
        agri = [pr for pr in profs if any(k in pr["landuse"] for k in AGRI_LANDUSE) and np.isfinite(pr["nfkwe"])]
        use = agri or [pr for pr in profs if np.isfinite(pr["nfkwe"])]
        w = np.array([pr["share"] for pr in use])
        v = np.array([pr["nfkwe"] for pr in use])
        mean = float(np.average(v, weights=w))
        sd = float(np.sqrt(np.average((v - mean) ** 2, weights=w)))
        rows.append(dict(unit=unit, nfkwe_mm=mean, sd_between_profiles_mm=sd, n_profiles=len(use),
                         agricultural_only=bool(agri), profiles=[(pr["landuse"], pr["share"], round(pr["nfkwe"], 1),
                                                                  pr["we_dm"]) for pr in profs]))
    return pd.DataFrame(rows).set_index("unit")


# ---------------------------------------------------------------- Bodenzahl model (trained on the west)

def bodenzahl_model(numeric: dict[str, np.ndarray], unit: np.ndarray, bz: np.ndarray, parcel_id: np.ndarray,
                    predict_mask: np.ndarray) -> dict:
    """Predict Bodenzahl from coarse covariates, trained on pixels inside the downloaded parcels.

    Candidates, compared by cross-validation grouped by parcel (each parcel has one Bodenzahl, so
    pixels of a parcel are not independent): farm mean, BÜK200 unit mean, gradient boosting on the
    covariates + unit. The best one is refitted on all parcels and predicts `predict_mask`.
    """
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.model_selection import GroupKFold

    names = list(numeric)
    ucodes, uinv = np.unique(np.nan_to_num(unit, nan=-1), return_inverse=True)
    X = np.stack([numeric[n] for n in names] + [uinv.reshape(unit.shape).astype("float64")], -1)
    cat = [False] * len(names) + [True]
    tr = (parcel_id > 0) & np.isfinite(bz)
    Xt, yt, gt = X[tr], bz[tr], parcel_id[tr]
    n_groups = len(np.unique(gt))

    def unit_mean_fit(Xa, ya):
        means = pd.Series(ya).groupby(Xa[:, -1]).mean()
        return lambda Xb: pd.Series(Xb[:, -1]).map(means).fillna(ya.mean()).to_numpy()

    def hgb_fit(Xa, ya):
        m = HistGradientBoostingRegressor(max_iter=200, learning_rate=0.05, max_leaf_nodes=7, min_samples_leaf=100,
                                          l2_regularization=1.0, categorical_features=cat, random_state=0).fit(Xa, ya)
        return m.predict

    fitters = {"farm_mean": lambda Xa, ya: (lambda Xb: np.full(len(Xb), ya.mean())),
               "unit_mean": unit_mean_fit, "gradient_boosting": hgb_fit}
    scores = {}
    for name, fit in fitters.items():
        oof = np.full(yt.shape, np.nan)
        for a, b in GroupKFold(n_splits=5).split(Xt, yt, gt):
            oof[b] = fit(Xt[a], yt[a])(Xt[b])
        # score per parcel (one official value each), not per pixel
        per = pd.DataFrame(dict(g=gt, y=yt, p=oof)).groupby("g").mean()
        scores[name] = dict(rmse_parcel=float(np.sqrt(((per.p - per.y) ** 2).mean())),
                            mae_parcel=float((per.p - per.y).abs().mean()))
    best = min(scores, key=lambda k: scores[k]["rmse_parcel"])
    pred = np.full(bz.shape, np.nan, "float32")
    pred[predict_mask] = fitters[best](Xt, yt)(X[predict_mask])
    return dict(pred=pred, best=best, scores=scores, n_parcels=n_groups, n_px=int(tr.sum()),
                rmse=scores[best]["rmse_parcel"], features=names + ["buek_unit"])
