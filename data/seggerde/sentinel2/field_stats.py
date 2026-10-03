# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "pandas", "geopandas", "exactextract", "matplotlib", "shapely"]
# ///
"""Per-field NDVI statistics, relative productivity and stability zones.

    uv run field_stats.py

Inputs (written by fetch_s2.py): ndvi_stack_<year>.tif, ndvi_peak_<year>.tif.
Field polygons: ../clean/fields_clean.geojson if it exists (respects `use_for_stats`),
else ../fields_active.geojson. The file used is recorded in field_stats_meta.json.

Outputs
- field_ndvi_timeseries.csv  long: plotId, fieldName, date, obs_id, ndvi_mean/p10/p50/p90,
                             valid_fraction, stat_zone (inner20m | full_field_fallback), use_for_stats
- relative_productivity.tif  band1 mean of per-season NDVI_p90/field mean, band2 inter-season SD
                             of that ratio, band3 mean within-field z-score, band4 SD of z,
                             band5 n seasons used
- yield_potential_zones.tif  uint8: 1 stable-high, 2 stable-low, 3 unstable, 0 none
- field_summary.csv          one row per field
- quicklook_*.png
"""
from __future__ import annotations

import json
import re
import time
import warnings
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from exactextract import exact_extract
from rasterio.features import rasterize

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import BoundaryNorm, LinearSegmentedColormap, ListedColormap  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning)
HERE = Path(__file__).resolve().parent
CLEAN = HERE.parent / "clean" / "fields_clean.geojson"
ACTIVE = HERE.parent / "fields_active.geojson"
CRS = "EPSG:32632"
INNER_M = 20
MIN_FIELD_VALID = 0.5      # time-series row counted as a valid observation when >= 50 % of the zone is clear
MIN_SEASON_PEAK = 0.40     # field-season skipped for normalisation if inner-zone mean peak NDVI below this
MIN_PEAK_OBS = 2           # pixel needs >= 2 clear May-Jul observations for its peak value
MIN_SEASONS = 3            # pixel needs >= 3 usable seasons for a zone
UNSTABLE_SD_Z = 1.0        # SD across seasons of the within-field z-score above which a pixel is "unstable"
ZONE_INNER_M = 10          # zoning uses pixels whose centre is >= 10 m inside the field (drops mixed edge pixels)
MIN_ZONE_PX = 20           # fields with < 20 such pixels (0.2 ha) get no zones
SD_FLOOR = 0.02            # NDVI; floor on the within-field SD so near-uniform (saturated) seasons don't turn noise into big z
ZONES = {0: "none", 1: "stable_high", 2: "stable_low", 3: "unstable"}


def load_fields():
    src = CLEAN if CLEAN.exists() else ACTIVE
    g = gpd.read_file(src).to_crs(CRS)
    if "use_for_stats" not in g:
        g["use_for_stats"] = True
    g["use_for_stats"] = g["use_for_stats"].astype(bool)
    inner = g.geometry.buffer(-INNER_M)
    empty = inner.is_empty | (inner.area <= 0)
    g["stat_zone"] = np.where(empty, "full_field_fallback", "inner20m")
    g["zone_geom"] = inner.where(~empty, g.geometry)
    g["zone_area_m2"] = gpd.GeoSeries(g["zone_geom"], crs=CRS).area
    g["field_area_ha"] = g.geometry.area / 1e4
    return g, src


def timeseries(g):
    zones = gpd.GeoDataFrame(g[["plotId", "fieldName", "stat_zone", "use_for_stats", "zone_area_m2"]],
                             geometry=g["zone_geom"], crs=CRS)
    rows = []
    for tif in sorted(HERE.glob("ndvi_stack_*.tif")):
        with rasterio.open(tif) as r:
            desc = r.descriptions
        t0 = time.time()
        df = exact_extract(str(tif), zones,
                           ["mean", "quantile(q=0.1)", "quantile(q=0.5)", "quantile(q=0.9)", "count"],
                           include_cols=["plotId"], output="pandas")
        long = df.melt(id_vars="plotId")
        m = long["variable"].str.extract(r"band_(\d+)_(.*)")
        long["band"] = m[0].astype(int)
        long["stat"] = m[1]
        wide = long.pivot_table(index=["plotId", "band"], columns="stat", values="value").reset_index()
        rows.append(wide.assign(obs_id=wide["band"].map(lambda b: desc[b - 1])))
        print(f"{tif.name}: {len(desc)} scenes, {time.time() - t0:.1f}s", flush=True)
    ts = pd.concat(rows, ignore_index=True)
    ren = {c: c for c in ts.columns}
    for c in ts.columns:
        if c.startswith("quantile"):
            q = re.findall(r"\d+", c)[-1]
            ren[c] = f"ndvi_p{int(q):02d}" if len(q) <= 2 else c
    ts = ts.rename(columns=ren)
    ts = ts.merge(zones.drop(columns="geometry"), on="plotId")
    ts["valid_fraction"] = (ts["count"] * 100.0 / ts["zone_area_m2"]).clip(upper=1).round(4)
    for c in ["mean", "ndvi_p10", "ndvi_p50", "ndvi_p90"]:
        ts[c] = ts[c] / 10000.0
    ts = ts.rename(columns={"mean": "ndvi_mean"})
    ts["date"] = ts["obs_id"].str[:10]
    ts = ts[ts["count"] > 0]
    ts["valid_obs"] = ts["valid_fraction"] >= MIN_FIELD_VALID
    cols = ["plotId", "fieldName", "date", "obs_id", "ndvi_mean", "ndvi_p10", "ndvi_p50", "ndvi_p90",
            "valid_fraction", "valid_obs", "stat_zone", "use_for_stats"]
    ts = ts[cols].sort_values(["fieldName", "date", "obs_id"])
    for c in ["ndvi_mean", "ndvi_p10", "ndvi_p50", "ndvi_p90"]:
        ts[c] = ts[c].round(4)
    return ts


def productivity(g):
    peaks = sorted(HERE.glob("ndvi_peak_*.tif"))
    with rasterio.open(peaks[0]) as r:
        prof, shape, tr = r.profile, r.shape, r.transform
    gs = g[g["use_for_stats"]].reset_index(drop=True)
    ids = np.arange(1, len(gs) + 1)
    # field id per pixel (pixel centre inside the 10 m inner buffer). Smaller fields drawn last so they win overlaps.
    order = gs["field_area_ha"].sort_values(ascending=False).index
    inner10 = gs.geometry.buffer(-ZONE_INNER_M)
    fin = rasterize([(inner10[i], ids[i]) for i in order if not inner10[i].is_empty],
                    out_shape=shape, transform=tr, fill=0, dtype="int32")
    fid = np.where(fin > 0, fin, 0)  # zoning / normalisation pixel set = inner 10 m
    for k in ids:
        if (fid == k).sum() < MIN_ZONE_PX:
            fid[fid == k] = 0; fin[fin == k] = 0
    rels, zs, seasons, per_fs = [], [], [], []
    for p in peaks:
        year = int(p.stem.split("_")[-1])
        with rasterio.open(p) as r:
            p90, nobs = r.read(1), r.read(3)
        p90 = np.where(nobs >= MIN_PEAK_OBS, p90, np.nan)
        rel = np.full(shape, np.nan, np.float32)
        z = np.full(shape, np.nan, np.float32)
        for i, k in enumerate(ids):
            inn = (fin == k) & np.isfinite(p90)
            n_inner = int((fin == k).sum())
            rec = dict(plotId=gs.plotId[i], season=year, n_inner_px=n_inner, n_inner_px_valid=int(inn.sum()))
            if n_inner == 0 or inn.sum() < max(3, 0.5 * n_inner):
                rec.update(status="insufficient_clear_peak_pixels")
                per_fs.append(rec)
                continue
            v = p90[inn]
            mu, sd = float(v.mean()), float(v.std())
            rec.update(peak_mean=round(mu, 4), peak_sd=round(sd, 4), peak_cv=round(sd / mu, 4) if mu > 0 else np.nan)
            if mu < MIN_SEASON_PEAK:
                rec.update(status=f"low_peak<{MIN_SEASON_PEAK}")
                per_fs.append(rec)
                continue
            rec.update(status="used")
            per_fs.append(rec)
            sel = fid == k
            rel[sel] = p90[sel] / mu
            z[sel] = (p90[sel] - mu) / max(sd, SD_FLOOR)
        rels.append(rel); zs.append(z); seasons.append(year)
    R, Z = np.stack(rels), np.stack(zs)
    n = np.isfinite(Z).sum(0)
    ok = n >= MIN_SEASONS
    mean_rel = np.where(ok, np.nanmean(R, 0), np.nan)
    sd_rel = np.where(ok, np.nanstd(R, 0), np.nan)
    mean_z = np.where(ok, np.nanmean(Z, 0), np.nan)
    sd_z = np.where(ok, np.nanstd(Z, 0), np.nan)
    zone = np.zeros(shape, np.uint8)
    zone[ok & (sd_z > UNSTABLE_SD_Z)] = 3
    zone[ok & (sd_z <= UNSTABLE_SD_Z) & (mean_z > 0)] = 1
    zone[ok & (sd_z <= UNSTABLE_SD_Z) & (mean_z <= 0)] = 2
    base = dict(driver="GTiff", width=shape[1], height=shape[0], crs=CRS, transform=tr,
                compress="deflate", tiled=True, blockxsize=256, blockysize=256)
    with rasterio.open(HERE / "relative_productivity.tif", "w", count=5, dtype="float32", nodata=np.nan,
                       predictor=3, **base) as d:
        for b, (a, name) in enumerate(zip([mean_rel, sd_rel, mean_z, sd_z, n.astype(np.float32)],
                                          ["mean_rel_ndvi_peak", "sd_rel_ndvi_peak", "mean_z_within_field",
                                           "sd_z_within_field", "n_seasons"]), 1):
            d.write(a.astype("float32"), b); d.set_band_description(b, name)
    with rasterio.open(HERE / "yield_potential_zones.tif", "w", count=1, dtype="uint8", nodata=0, **base) as d:
        d.write(zone, 1)
        d.set_band_description(1, "1=stable_high 2=stable_low 3=unstable 0=none")
        d.write_colormap(1, {0: (0, 0, 0, 0), 1: (42, 120, 214, 255), 2: (227, 73, 72, 255), 3: (237, 161, 0, 255)})
    fs = pd.DataFrame(per_fs)
    pix = []
    for i, k in enumerate(ids):
        sel = fid == k
        zz = zone[sel]
        tot = max(int(sel.sum()), 1)
        if sel.sum() == 0:
            pix.append(dict(plotId=gs.plotId[i], n_zone_px=0)); continue
        mr = mean_rel[sel]
        pix.append(dict(plotId=gs.plotId[i], n_zone_px=int(sel.sum()),
                        share_stable_high=round((zz == 1).sum() / tot, 3),
                        share_stable_low=round((zz == 2).sum() / tot, 3),
                        share_unstable=round((zz == 3).sum() / tot, 3),
                        share_no_zone=round((zz == 0).sum() / tot, 3),
                        rel_p10=round(float(np.nanpercentile(mr, 10)), 4) if np.isfinite(mr).any() else np.nan,
                        rel_p90=round(float(np.nanpercentile(mr, 90)), 4) if np.isfinite(mr).any() else np.nan,
                        mean_sd_z=round(float(np.nanmean(sd_z[sel])), 3) if np.isfinite(sd_z[sel]).any() else np.nan))
    return fs, pd.DataFrame(pix), dict(mean_rel=mean_rel, zone=zone, tr=tr, shape=shape, seasons=seasons)


def summary(g, ts, fs, pix):
    s = g[["plotId", "fieldName", "field_area_ha", "use_for_stats", "stat_zone"]].copy()
    s["field_area_ha"] = s["field_area_ha"].round(3)
    v = ts[ts["valid_obs"]].assign(season=lambda d: d["date"].str[:4].astype(int))
    nobs = v.pivot_table(index="plotId", columns="season", values="date", aggfunc="count").add_prefix("n_obs_")
    ts_peak = v[v["date"].str[5:7].isin(["05", "06", "07"])].pivot_table(
        index="plotId", columns="season", values="ndvi_mean", aggfunc="max").round(3).add_prefix("ts_max_MayJul_")
    pk = fs.pivot_table(index="plotId", columns="season", values="peak_mean").round(3).add_prefix("peak_p90_")
    cv = fs.pivot_table(index="plotId", columns="season", values="peak_cv").add_prefix("cv_")
    st = fs.pivot_table(index="plotId", columns="season", values="status", aggfunc="first").add_prefix("status_")
    used = fs[fs["status"] == "used"].groupby("plotId").agg(n_seasons_used=("season", "count"),
                                                            mean_within_field_cv=("peak_cv", "mean"))
    s = (s.set_index("plotId").join([nobs, ts_peak, pk, used]).join(pix.set_index("plotId"))
         .join(cv.round(4)).join(st).reset_index())
    s["mean_within_field_cv"] = s["mean_within_field_cv"].round(4)
    return s


def quicklooks(g, ts, s, prod):
    INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": MUTED, "axes.labelcolor": INK,
                         "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                         "axes.spines.right": False, "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb"})
    # 1. time series: 6 largest stats fields, small multiples
    big = s[s["use_for_stats"]].sort_values("field_area_ha", ascending=False).head(6)
    fig, axs = plt.subplots(len(big), 1, figsize=(11, 1.7 * len(big)), sharex=True, sharey=True)
    for ax, (_, f) in zip(axs, big.iterrows()):
        d = ts[(ts["plotId"] == f["plotId"]) & ts["valid_obs"]].copy()
        d["date"] = pd.to_datetime(d["date"])
        for _, seg in d.groupby(d["date"].dt.year):  # one segment per season, no line across winter
            ax.fill_between(seg["date"], seg["ndvi_p10"], seg["ndvi_p90"], color="#9ec5f4", alpha=0.6, lw=0)
            ax.plot(seg["date"], seg["ndvi_mean"], color="#2a78d6", lw=1.2, marker="o", ms=2.5)
        ax.set_title(f"{f['fieldName']}  ({f['field_area_ha']:.1f} ha)", loc="left", fontsize=9, color=INK)
        ax.grid(axis="y", color=GRID, lw=0.6); ax.set_ylim(-0.1, 1.0); ax.set_ylabel("NDVI")
    axs[0].text(1, 1.15, "line = zone mean, band = p10–p90 within field; clear observations only (Mar–Oct)",
                transform=axs[0].transAxes, ha="right", fontsize=8, color=MUTED)
    fig.suptitle("Sentinel-2 NDVI per field, 2019–2026 (6 largest fields, 20 m inner zone)", x=0.01, ha="left", color=INK)
    fig.tight_layout(); fig.savefig(HERE / "quicklook_timeseries.png", dpi=130); plt.close(fig)

    x0, y1 = prod["tr"].c, prod["tr"].f
    ext = [x0, x0 + prod["shape"][1] * 10, y1 - prod["shape"][0] * 10, y1]
    gs = g[g["use_for_stats"]]
    # 2. relative productivity map (diverging red - gray - blue)
    cmap = LinearSegmentedColormap.from_list("div", ["#a83232", "#e34948", "#f0efec", "#3987e5", "#184f95"])
    cmap.set_bad((1, 1, 1, 0))
    fig, ax = plt.subplots(figsize=(8.5, 9.5))
    im = ax.imshow(prod["mean_rel"], extent=ext, cmap=cmap, vmin=0.85, vmax=1.15, interpolation="nearest")
    g.boundary.plot(ax=ax, color=INK, lw=0.5)
    cb = fig.colorbar(im, ax=ax, shrink=0.6, label="peak NDVI / field mean, averaged over seasons")
    ax.set_title(f"Multi-year relative productivity (seasons {min(prod['seasons'])}–{max(prod['seasons'])}, "
                 f"May–Jul p90 NDVI)", loc="left", color=INK)
    ax.set_xlabel("UTM 32N easting (m)"); ax.set_ylabel("northing (m)"); ax.ticklabel_format(style="plain")
    fig.tight_layout(); fig.savefig(HERE / "quicklook_relative_productivity.png", dpi=140); plt.close(fig)
    # 3. zones
    zc = ListedColormap([(0, 0, 0, 0), "#2a78d6", "#e34948", "#eda100"])
    fig, ax = plt.subplots(figsize=(8.5, 9.5))
    ax.imshow(prod["zone"], extent=ext, cmap=zc, norm=BoundaryNorm([-0.5, 0.5, 1.5, 2.5, 3.5], 4), interpolation="nearest")
    g.boundary.plot(ax=ax, color=INK, lw=0.5)
    for _, f in gs.sort_values("field_area_ha", ascending=False).head(15).iterrows():
        p = f.geometry.representative_point()
        ax.annotate(f["fieldName"], (p.x, p.y), fontsize=6.5, ha="center", color=INK,
                    bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.7))
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color="#2a78d6", label="stable high"), Patch(color="#e34948", label="stable low"),
                       Patch(color="#eda100", label=f"unstable (SD of z > {UNSTABLE_SD_Z})")],
              loc="lower left", frameon=True, fontsize=8)
    ax.set_title("Yield-potential zones from NDVI stability (within-field z-score)", loc="left", color=INK)
    ax.set_xlabel("UTM 32N easting (m)"); ax.set_ylabel("northing (m)"); ax.ticklabel_format(style="plain")
    fig.tight_layout(); fig.savefig(HERE / "quicklook_zones.png", dpi=140); plt.close(fig)


def main():
    g, src = load_fields()
    print(f"fields: {src} ({len(g)} features, {int(g.use_for_stats.sum())} use_for_stats, "
          f"{int((g.stat_zone == 'full_field_fallback').sum())} full-field fallbacks)")
    ts = timeseries(g)
    ts.to_csv(HERE / "field_ndvi_timeseries.csv", index=False)
    fs, pix, prod = productivity(g)
    fs.to_csv(HERE / "field_season_peaks.csv", index=False)
    s = summary(g, ts, fs, pix)
    s.to_csv(HERE / "field_summary.csv", index=False)
    quicklooks(g, ts, s, prod)
    json.dump(dict(fields_file=str(src.relative_to(HERE.parent)), n_fields=len(g),
                   n_use_for_stats=int(g.use_for_stats.sum()),
                   full_field_fallback=g.loc[g.stat_zone == "full_field_fallback", "fieldName"].tolist(),
                   inner_buffer_m=INNER_M, min_field_valid=MIN_FIELD_VALID, min_season_peak=MIN_SEASON_PEAK,
                   min_peak_obs=MIN_PEAK_OBS, min_seasons=MIN_SEASONS, unstable_sd_z=UNSTABLE_SD_Z,
                   zone_inner_m=ZONE_INNER_M, min_zone_px=MIN_ZONE_PX, sd_floor=SD_FLOOR,
                   seasons=prod["seasons"], run=time.strftime("%Y-%m-%dT%H:%M:%S")),
              open(HERE / "field_stats_meta.json", "w"), indent=1, ensure_ascii=False)
    print("done")


if __name__ == "__main__":
    main()
