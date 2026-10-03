# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "pandas", "geopandas", "shapely", "pyproj", "pillow", "scipy", "scikit-learn"]
# ///
"""Validate yield potential v1 without harvest data. Run after build_store.py.

    uv run poc/validate.py      # writes the `validation` table in poc/store/soil.sqlite and poc/VALIDATION.md

1. Leave one season out: predict the held-out season's relative NDVI map from the other seasons.
   Compared: flat (field mean), plain NDVI mean, water-scaled NDVI, v1 (water-scaled + shrinkage).
2. Dry seasons (2022, 2025) reported separately: does water scaling help where it should?
3. Bodenzahl (west): between fields and, where the downloaded parcels split a field, within fields.
4. Soil/terrain model: grouped-CV R² over all fields and the west only.
5. Derived soil layers: Bodenzahl model scores (grouped by parcel) and the nFK lookup per BÜK200 unit.
"""
from __future__ import annotations

import json
import sqlite3
import warnings
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from scipy.stats import binomtest, spearmanr

from build_store import RUN_DIR, RUN_ID, SEG, STORE, UTM, load_grid, nanmedian3
from lib import yield_model as ym

warnings.filterwarnings("ignore", category=RuntimeWarning)
POC = Path(__file__).resolve().parent
DRY_SEASONS = (2022, 2025)
MIN_PX = 50  # pixels per field-season for a per-field score
SHRINK_SWEEP = (4, 32, 256, 1e9)  # 1e9 ≈ no water scaling


def read(path: Path, band: str | int = 1) -> np.ndarray:
    with rasterio.open(path) as r:
        return r.read(band if isinstance(band, int) else r.descriptions.index(band) + 1)


def loyo(seasons: ym.Seasons, cwb: pd.Series, soil_pred: np.ndarray) -> pd.DataFrame:
    rows = []
    for s_idx, year in enumerate(seasons.years):
        train = [y for y in seasons.years if y != year]
        nd = ym.ndvi_component(seasons, cwb, use=train)
        plain = nanmedian3(nd.level)
        scaled = nanmedian3(nd.at(float(cwb[year])))
        w = ym.ndvi_weight(nd, seasons.fid)
        v1 = np.where(np.isfinite(scaled), w * scaled + (1 - w) * soil_pred, np.nan)
        obs = seasons.rel[s_idx]
        for k in np.unique(seasons.fid[seasons.fid > 0]):
            sel = (seasons.fid == k) & np.isfinite(obs) & np.isfinite(scaled)
            if sel.sum() < MIN_PX:
                continue
            o = obs[sel]
            rec = dict(season=year, field=int(k), n_px=int(sel.sum()))
            for name, pred in (("plain", plain), ("scaled", scaled), ("v1", v1)):
                p = pred[sel]
                rec[f"rho_{name}"] = spearmanr(p, o).statistic
                rec[f"rmse_{name}"] = float(np.sqrt(np.mean((p - o) ** 2)))
                rec[f"agree_{name}"] = float(np.mean(np.sign(p - 1) == np.sign(o - 1)))
            rec["rmse_flat"] = float(np.sqrt(np.mean((o - 1) ** 2)))
            rows.append(rec)
    return pd.DataFrame(rows)


def bodenzahl_checks(fields: gpd.GeoDataFrame, yp: np.ndarray, bz: np.ndarray, transform) -> dict:
    from rasterio.features import rasterize
    out = {}
    # between fields: official Bodenzahl at the field's sample point vs year-normalised field peak NDVI rank
    nib = pd.read_csv(SEG / "nibis" / "nibis_fields.csv").dropna(subset=["L849_BODENZ"])
    peaks = pd.read_csv(SEG / "sentinel2" / "field_season_peaks.csv")
    peaks = peaks[peaks.status == "used"]
    peaks["pct"] = peaks.groupby("season").peak_mean.rank(pct=True)
    rank = peaks.groupby("plotId").pct.mean()
    j = nib.set_index("plotId").join(rank, how="inner")
    r = spearmanr(j.L849_BODENZ, j.pct)
    out["between"] = dict(rho=float(r.statistic), p=float(r.pvalue), n=len(j))
    # within field: fields split by ≥ 2 Bodenzahl values (each with ≥ 20 pixels)
    pairs = []
    for f in fields.itertuples():
        m = rasterize([f.geometry.buffer(-10)], out_shape=yp.shape, transform=transform, fill=0,
                      dtype="uint8").astype(bool) if not f.geometry.buffer(-10).is_empty else None
        if m is None:
            continue
        v = bz[m & np.isfinite(bz) & np.isfinite(yp)]
        vals = [u for u in np.unique(v) if (v == u).sum() >= 20]
        if len(vals) < 2:
            continue
        lo_v, hi_v = min(vals), max(vals)
        y_lo = float(np.nanmean(yp[m & (bz == lo_v)]))
        y_hi = float(np.nanmean(yp[m & (bz == hi_v)]))
        pairs.append(dict(field=f.fieldName, bz_low=float(lo_v), bz_high=float(hi_v), yp_low=y_lo, yp_high=y_hi,
                          agrees=y_hi > y_lo))
    n_ok = sum(p["agrees"] for p in pairs)
    out["within"] = dict(n=len(pairs), n_agree=n_ok,
                         p=float(binomtest(n_ok, len(pairs), 0.5, alternative="greater").pvalue) if pairs else None,
                         pairs=pairs)
    return out


def soil_model_cv(fields, seasons, transform, shape) -> dict:
    reg = RUN_DIR / "regional"
    dem = RUN_DIR / "covariates" / "dem__copernicus.tif"
    covs = {"clay": read(reg / "texture__soilgrids.tif"), "sand": read(Path(SEG / "soilgrids" / "s2grid" / "sand.tif"), "0-5cm_Q0.5"),
            "soc": read(reg / "soc__soilgrids.tif"), "nfk": read(reg / "nfk__soilgrids.tif"),
            "bodenzahl": read(reg / "bodenzahl__lbeg_bodenschaetzung.tif"),
            "twi": read(dem, "twi"), "slope": read(dem, "slope"), "rel_elev": read(dem, "rel_elev")}
    nd = ym.ndvi_component(seasons, ym.cwb_apr_jun(SEG / "era5_history" / "daily.csv", SEG / "era5_history" / "cells.csv"))
    fall, _ = ym.field_index(fields, transform, shape)
    all_ = ym.soil_model(covs, nd.level, fall, seasons.fid)
    west_ids = set(pd.read_csv(SEG / "nibis" / "nibis_fields.csv").query("L816_area_share > 0 or L849_area_share > 0").plotId)
    keep = [i + 1 for i, p in enumerate(seasons.plot_ids) if p in west_ids]
    west = ym.soil_model(covs, nd.level, fall, np.where(np.isin(seasons.fid, keep), seasons.fid, 0))
    return dict(all=dict(r2=all_.r2_oof, n_px=all_.n_train, resid_sd=all_.resid_sd),
                west=dict(r2=west.r2_oof, n_px=west.n_train, resid_sd=west.resid_sd))


def write_db(rows: list[tuple]):
    conn = sqlite3.connect(STORE / "soil.sqlite")
    conn.execute("DELETE FROM validation WHERE run_id = ?", (RUN_ID,))
    conn.executemany("INSERT INTO validation VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    conn.close()


def main():
    transform, H, W = load_grid()
    fields = gpd.read_file(SEG / "clean" / "fields_clean.geojson").to_crs(UTM)
    seasons = ym.season_rel(fields, SEG / "sentinel2", transform, (H, W))
    cwb = ym.cwb_apr_jun(SEG / "era5_history" / "daily.csv", SEG / "era5_history" / "cells.csv")
    soil_pred = read(RUN_DIR / "covariates" / "yield_components.tif", "soil_model")

    sweep = []
    default_k = ym.SLOPE_SHRINK_K
    for k in SHRINK_SWEEP:
        ym.SLOPE_SHRINK_K = k
        lk = loyo(seasons, cwb, soil_pred)
        dk = lk[lk.season.isin(DRY_SEASONS)]
        sweep.append(dict(k=k, rho_v1=lk.rho_v1.median(), rmse_v1=lk.rmse_v1.median(), rho_v1_dry=dk.rho_v1.median(),
                          scaled_beats_plain=float((lk.rmse_scaled < lk.rmse_plain).mean())))
    ym.SLOPE_SHRINK_K = default_k
    lo = loyo(seasons, cwb, soil_pred)
    names = ["plain", "scaled", "v1"]
    by_season = lo.groupby("season").agg(
        n_fields=("field", "size"), **{f"rho_{n}": (f"rho_{n}", "median") for n in names},
        **{f"rmse_{n}": (f"rmse_{n}", "median") for n in names + ["flat"]},
        **{f"agree_{n}": (f"agree_{n}", "median") for n in names})
    overall = lo[[c for c in lo.columns if c.startswith(("rho_", "rmse_", "agree_"))]].median()
    dry = lo[lo.season.isin(DRY_SEASONS)]
    # paired: does water scaling beat plain in each field-season?
    win_all = float((lo.rmse_scaled < lo.rmse_plain).mean())
    win_dry = float((dry.rmse_scaled < dry.rmse_plain).mean())
    v1_vs_flat = float((lo.rmse_v1 < lo.rmse_flat).mean())

    bz = bodenzahl_checks(fields, read(RUN_DIR / "regional" / "yield_potential__derived.tif"),
                          read(RUN_DIR / "regional" / "bodenzahl__lbeg_bodenschaetzung.tif"), transform)
    sm = soil_model_cv(fields, seasons, transform, (H, W))

    rows = []
    for k, v in overall.items():
        rows.append((RUN_ID, f"loyo_{k}_median", "all_seasons", float(v), int(len(lo)), None))
    for yr, r in by_season.iterrows():
        rows.append((RUN_ID, "loyo_season", str(yr), float(r.rho_v1), int(r.n_fields), r.to_json()))
    rows += [(RUN_ID, "loyo_share_scaled_beats_plain_rmse", "all_seasons", win_all, len(lo), None),
             (RUN_ID, "loyo_share_scaled_beats_plain_rmse", "dry_seasons", win_dry, len(dry), None),
             (RUN_ID, "loyo_share_v1_beats_flat_rmse", "all_seasons", v1_vs_flat, len(lo), None),
             (RUN_ID, "bodenzahl_between_fields_spearman", "west", bz["between"]["rho"], bz["between"]["n"],
              json.dumps(bz["between"])),
             (RUN_ID, "bodenzahl_within_field_agree_share", "west",
              bz["within"]["n_agree"] / bz["within"]["n"] if bz["within"]["n"] else None, bz["within"]["n"],
              json.dumps(bz["within"])),
             (RUN_ID, "soil_model_r2_grouped_cv", "all_fields", sm["all"]["r2"], sm["all"]["n_px"], json.dumps(sm["all"])),
             (RUN_ID, "soil_model_r2_grouped_cv", "west", sm["west"]["r2"], sm["west"]["n_px"], json.dumps(sm["west"]))]

    ds = json.loads((RUN_DIR / "covariates" / "derived_soil.json").read_text())
    bm = ds["bodenzahl_model"]
    for name, sc in bm["scores"].items():
        rows.append((RUN_ID, "bodenzahl_derived_rmse_grouped_by_parcel", name, sc["rmse_parcel"], bm["n_parcels"], json.dumps(sc)))
    for r in sweep:
        rows.append((RUN_ID, "loyo_shrink_sweep", f"k={r['k']:g}", r["rho_v1"], len(lo), json.dumps(r)))
    write_db(rows)
    md = render_md(lo, by_season, overall, win_all, win_dry, v1_vs_flat, bz, sm, cwb, sweep, ds)
    (POC / "VALIDATION.md").write_text(md)
    print(md)


def render_md(lo, by_season, overall, win_all, win_dry, v1_vs_flat, bz, sm, cwb, sweep, ds) -> str:
    f2 = lambda x: f"{x:.2f}"
    f3 = lambda x: f"{x:.3f}"
    season_rows = "\n".join(
        f"| {yr}{' (dry)' if yr in DRY_SEASONS else ''} | {cwb[yr]:.0f} | {int(r.n_fields)} | {f2(r.rho_plain)} | {f2(r.rho_scaled)} | "
        f"{f2(r.rho_v1)} | {f3(r.rmse_flat)} | {f3(r.rmse_plain)} | {f3(r.rmse_v1)} | {f2(r.agree_v1)} |"
        for yr, r in by_season.iterrows())
    sweep_rows = "\n".join(
        f"| {'off (no water scaling)' if r['k'] >= 1e8 else int(r['k'])}{' **(used)**' if r['k'] == ym.SLOPE_SHRINK_K else ''} | "
        f"{f2(r['rho_v1'])} | {f3(r['rmse_v1'])} | {f2(r['rho_v1_dry'])} | {r['scaled_beats_plain']:.0%} |" for r in sweep)
    bm = ds["bodenzahl_model"]
    label = {"farm_mean": "Farm mean (no model)", "unit_mean": "BÜK200 unit mean", "gradient_boosting": "Gradient boosting (covariates + unit)"}
    bz_rows = "\n".join(f"| {label[k]}{' **(used)**' if k == bm['chosen'] else ''} | {v['rmse_parcel']:.1f} | {v['mae_parcel']:.1f} |"
                         for k, v in bm["scores"].items())
    nfk_rows = "\n".join(f"| {u} | {v['nfkwe_mm']:.0f} | {v['sd_between_profiles_mm']:.0f} | {v['n_profiles']} |"
                          for u, v in ds["nfk_units"].items())
    within = bz["within"]
    within_rows = "\n".join(f"| {p['field']} | {p['bz_low']:.0f} → {p['bz_high']:.0f} | {p['yp_low']:.1f} → {p['yp_high']:.1f} | "
                            f"{'yes' if p['agrees'] else 'no'} |" for p in within["pairs"]) or "| – | – | – | – |"
    return f"""# Yield potential v1: validation

Run `{RUN_ID}`, built from data on disk only. Generated by `uv run poc/validate.py`; numbers are also in
the `validation` table of `poc/store/soil.sqlite`.

There is **no harvest data**, so nothing here measures yield. What can be tested is whether the map
predicts **next season's within-field NDVI pattern**, and whether it agrees with the official soil survey.

## 1. Leave one season out

For each season 2019–2026, the map is rebuilt from the other seven and compared with the held-out
season's relative peak NDVI (pixel / field mean, inner 10 m zone, {len(lo)} field-seasons).

| Prediction | Median Spearman per field | Median RMSE | Above/below-mean agreement |
|---|---|---|---|
| Flat (field mean, no map) | – | {f3(overall.rmse_flat)} | 0.50 by construction |
| Plain multi-year NDVI mean | {f2(overall.rho_plain)} | {f3(overall.rmse_plain)} | {f2(overall.agree_plain)} |
| Water-scaled NDVI | {f2(overall.rho_scaled)} | {f3(overall.rmse_scaled)} | {f2(overall.agree_scaled)} |
| **v1** (water-scaled + shrinkage) | **{f2(overall.rho_v1)}** | **{f3(overall.rmse_v1)}** | **{f2(overall.agree_v1)}** |

- v1 beats the flat map in **{v1_vs_flat:.0%}** of field-seasons (RMSE).
- Water scaling beats the plain mean in **{win_all:.0%}** of field-seasons overall and **{win_dry:.0%}** in the dry seasons {DRY_SEASONS[0]} and {DRY_SEASONS[1]}.

### Water scaling: how much to trust each pixel's drought sensitivity

Each pixel's slope against the Apr–Jun water balance is shrunk toward its field's median with weight
n / (n + k). The leave-one-season-out score for each k:

| k | Spearman v1 | RMSE v1 | Spearman v1, dry seasons | Scaled beats plain (RMSE) |
|---|---|---|---|---|
{sweep_rows}

**Finding: water scaling adds no measurable skill.** Eight seasons are too few to estimate a per-pixel
drought response; weak shrinkage (k = 4) made the map worse, especially for the wet season 2021.
With k = 32 the scaled map is as good as the plain multi-year mean (slightly better in dry seasons),
so the dry/wet scenario views are kept but differ little from the normal one. v1's gain over the
plain mean comes from the per-field shrinkage (lower RMSE), not from the water balance.

### Per season

| Season | CWB Apr–Jun (mm) | Fields | ρ plain | ρ scaled | ρ v1 | RMSE flat | RMSE plain | RMSE v1 | Agreement v1 |
|---|---|---|---|---|---|---|---|---|---|
{season_rows}

## 2. Agreement with the official Bodenzahl (west, Niedersachsen)

- **Between fields:** official Bodenzahl at each field's sample point vs the field's average rank of
  peak NDVI among all fields in each season. Spearman ρ = **{bz['between']['rho']:.2f}** (p = {bz['between']['p']:.2f}, n = {bz['between']['n']} fields).
  Peak NDVI depends on the crop grown, and we have no rotation records, so this is a weak test.
- **Within fields:** only where the downloaded Bodenschätzung parcels split a field into parts with
  different Bodenzahl (≥ 20 pixels each). n = **{within['n']}**, higher-Bodenzahl part has higher yield
  potential in **{within['n_agree']}** (one-sided sign test p = {within['p'] if within['p'] is None else round(within['p'], 2)}).

| Field | Bodenzahl low → high | Yield potential low → high | Agrees |
|---|---|---|---|
{within_rows}

## 3. Soil/terrain model

Ridge on field-centred SoilGrids, Bodenzahl, TWI, slope and relative elevation, predicting the
multi-year relative NDVI level; cross-validation grouped by field.

| Scope | R² (grouped CV) | Pixels | Residual SD |
|---|---|---|---|
| All fields | {sm['all']['r2']:.3f} | {sm['all']['n_px']} | {sm['all']['resid_sd']:.4f} |
| West only | {sm['west']['r2']:.3f} | {sm['west']['n_px']} | {sm['west']['resid_sd']:.4f} |

R² ≈ 0: the coarse soil maps and the 30 m terrain don't explain within-field NDVI patterns across
fields (the terrain effect changes sign between wet and dry soils). In v1 the soil/terrain model is
therefore only a neutral prior: it fills the edge strip and fields without NDVI history, at low confidence.

## 4. Derived soil layers (`source = derived`)

### Bodenzahl

Trained on the {bm['n_parcels']} downloaded Bodenschätzung parcels in the west ({bm['n_px']} pixels), then applied to
the whole farm, including Sachsen-Anhalt. Features: {', '.join(bm['features'])}.
Cross-validation is grouped by parcel and scored per parcel (each parcel has one official value).

| Model | RMSE per parcel (points) | MAE per parcel (points) |
|---|---|---|
{bz_rows}

The model explains roughly half of the between-parcel variance, mostly through the BÜK200 unit.
The interval in the API is ±1.645 × the CV RMSE. In the east this is an extrapolation across the
state border (driver `extrapolated_across_state_border`); the soil units continue across it, but the
model was never checked there.

### nFK

nFKWe of the BÜK200 unit of the nearest sample point: each profile's horizons (KA5 Bodenart, bulk
density, humus) → available water per horizon from an **approximate** KA5 lookup → summed over the
effective rooting depth, stopping at permanently wet (Gr) horizons. Agricultural profiles only,
area-weighted. No capillary rise (as in BK50 nFKWe).

| BÜK200 unit | nFKWe (mm) | SD between profiles (mm) | Profiles |
|---|---|---|---|
{nfk_rows}

There is no nFK reference on disk (the downloaded BK50 attributes don't include nFKWe), so this layer is
not validated. It is far more discriminating than SoilGrids, which gives ~160–215 mm everywhere on this
sandy farm. Its interval combines the spread between profiles with ±30 mm (90 %) for the lookup itself.

## What is not validated

- **Yield itself.** NDVI is a proxy for vigour; validating yield needs yield-monitor or harvest data.
- **pH and SOC.** No independent reference is on disk; they carry SoilGrids' own uncertainty only.
- **nFK** (SoilGrids and derived). No reference on disk.
- **The dry/wet scenarios** beyond the 8 observed seasons (the per-pixel water sensitivity is fitted on
  CWB from {cwb.loc[2019:].min():.0f} to {cwb.loc[2019:].max():.0f} mm).
"""


if __name__ == "__main__":
    main()
