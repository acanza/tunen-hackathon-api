# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy", "scipy", "matplotlib"]
# ///
"""How have soil conditions on the Seggerde farm changed since 1950? Reads daily.csv from fetch.py.

Run from this folder:  uv run analyze.py

Farm values are the area-weighted mean of the 4 ERA5-Land cells (weights = active field area per cell).
Only complete years enter trends and period means. Baseline = 1961–1990 (WMO reference period).

Outputs:
  annual.csv            one row per year: farm-level indicators (see README for definitions)
  annual_by_cell.csv    the same per cell
  trends.csv            per indicator: Theil–Sen slope per decade, Mann–Kendall p, period means
  monthly_climate.csv   monthly mean soil moisture 0–100 cm and topsoil temperature, 1961–1990 vs 1996–2025
  ndvi_vs_soil.csv      2019–2026: farm peak NDVI vs growing-season soil moisture anomaly
  plot_annual.png, plot_monthly.png
  summary.json          numbers quoted in README.md
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).parent
SEG = HERE.parent
BASE = (1961, 1990)
RECENT = (1996, 2025)
GS = [4, 5, 6, 7, 8, 9]  # growing season Apr–Sep
OUT = {}

# palette: dataviz reference instance (light surface)
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, RED = "#2a78d6", "#eb6834", "#e34948"


def load():
    d = pd.read_csv(HERE / "daily.csv", parse_dates=["date"])
    cells = pd.read_csv(HERE / "cells.csv")
    w = cells.set_index("cell").area_ha / cells.area_ha.sum()
    num = [c for c in d.columns if c not in ("cell", "date")]
    farm = (d.assign(w=d.cell.map(w)).groupby("date")
            .apply(lambda g: pd.Series({c: np.average(g[c].dropna(), weights=g.w[g[c].notna()])
                                        if g[c].notna().any() else np.nan for c in num}), include_groups=False))
    return d, farm.reset_index(), cells


def annual(df):
    df = df.copy()
    df["year"], df["month"] = df.date.dt.year, df.date.dt.month
    base = df[df.year.between(*BASE)]
    p10 = base[base.month.isin(GS)].soil_moisture_0_to_100cm.quantile(0.10)
    gs = df[df.month.isin(GS)]
    g = df.groupby("year")
    a = pd.DataFrame({
        "days": g.size(),
        "sm_0_100_gs": gs.groupby("year").soil_moisture_0_to_100cm.mean(),
        "sm_0_7_gs": gs.groupby("year").soil_moisture_0_to_7cm.mean(),
        "sm_100_255_year": g.soil_moisture_100_to_255cm.mean(),
        "dry_days_gs": gs.groupby("year").soil_moisture_0_to_100cm.apply(lambda s: int((s < p10).sum())),
        "sm_0_100_gs_min": gs.groupby("year").soil_moisture_0_to_100cm.min(),
        "st_0_7_year": g.soil_temperature_0_to_7cm.mean(),
        "st_28_100_year": g.soil_temperature_28_to_100cm.mean(),
        "frost_days_topsoil": g.soil_temperature_0_to_7cm.apply(lambda s: int((s < 0).sum())),
        "t2m_year": g.temperature_2m_mean.mean(),
        "precip_year": g.precipitation_sum.sum(min_count=300),
        "et0_year": g.et0_fao_evapotranspiration.sum(min_count=300),
        "precip_gs": gs.groupby("year").precipitation_sum.sum(min_count=150),
        "et0_gs": gs.groupby("year").et0_fao_evapotranspiration.sum(min_count=150),
    })
    a["cwb_year"] = a.precip_year - a.et0_year
    a["cwb_gs"] = a.precip_gs - a.et0_gs
    a["complete"] = a.days >= 365
    return a, p10


def trend(a, col):
    s = a.loc[a.complete, col].dropna()
    x, y = s.index.values.astype(float), s.values
    sen = stats.theilslopes(y, x)  # robust, but 0 for counts that are mostly zero (dry_days_gs): use ols_slope there
    ols = stats.linregress(x, y)
    tau = stats.kendalltau(x, y)
    pm = lambda lo, hi: s[(s.index >= lo) & (s.index <= hi)].mean()
    return dict(indicator=col, first_year=int(x.min()), last_year=int(x.max()),
                sen_slope_per_decade=sen.slope * 10, sen_lo=sen.low_slope * 10, sen_hi=sen.high_slope * 10,
                ols_slope_per_decade=ols.slope * 10, mk_tau=tau.statistic, mk_p=tau.pvalue,
                mean_1961_1990=pm(*BASE), mean_1996_2025=pm(*RECENT), mean_2016_2025=pm(2016, 2025),
                change_recent_vs_base=pm(*RECENT) - pm(*BASE))


def style(ax):
    ax.set_facecolor(SURF)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(AXIS)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def plot_annual(a, p10, n_cells):
    a = a[a.complete]
    base = a.loc[BASE[0]:BASE[1]]
    fig, axes = plt.subplots(4, 1, figsize=(10, 11), sharex=True, facecolor=SURF)
    specs = [
        ("sm_0_100_gs", "Soil moisture 0–100 cm, Apr–Sep: difference from 1961–1990 (vol %)", 100, True),
        ("dry_days_gs", f"Dry days, Apr–Sep: soil moisture 0–100 cm below the 1961–1990 10th percentile ({p10*100:.1f} vol %)", 1, False),
        ("st_0_7_year", "Topsoil temperature 0–7 cm, annual mean (°C)", 1, False),
        ("cwb_gs", "Climatic water balance Apr–Sep, precipitation − ET₀ (mm)", 1, True),
    ]
    for ax, (col, title, k, diverging) in zip(axes, specs):
        style(ax)
        v = a[col] * k
        if diverging:
            ref = base[col].mean() * k if col.startswith("sm") else 0
            d = v - ref
            ax.bar(a.index, d, width=0.8, color=np.where(d >= 0, BLUE, RED), linewidth=0)
            ax.axhline(0, color=AXIS, lw=1)
            roll = d.rolling(11, center=True, min_periods=6).mean()
        elif col == "dry_days_gs":
            ax.bar(a.index, v, width=0.8, color=RED, linewidth=0)
            roll = v.rolling(11, center=True, min_periods=6).mean()
        else:
            ax.plot(a.index, v, color=BLUE, lw=1.2, alpha=0.55)
            roll = v.rolling(11, center=True, min_periods=6).mean()
        ax.plot(roll.index, roll, color=INK, lw=2)
        ax.set_title(title, loc="left", fontsize=10, color=INK, pad=6)
        lab = [y for y in (1976, 2003, 2018, 2022) if y in a.index]
        if col in ("sm_0_100_gs", "dry_days_gs"):
            yy = (v - (base[col].mean() * k if col.startswith("sm") else 0))
            for y in lab:
                ax.annotate(str(y), (y, yy[y]), xytext=(0, -11 if yy[y] < 0 else 3), textcoords="offset points",
                            ha="center", fontsize=7.5, color=INK2)
    axes[0].text(0.995, 1.02, "black line = 11-year centred mean", transform=axes[0].transAxes,
                 ha="right", va="bottom", fontsize=8, color=MUTED)
    axes[-1].set_xlim(a.index.min() - 1, a.index.max() + 1)
    fig.suptitle(f"LuF Seggerde: soil conditions 1950–2025 (ERA5-Land, farm mean of {n_cells} cells)",
                 x=0.07, ha="left", fontsize=12, color=INK, y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.985))
    fig.savefig(HERE / "plot_annual.png", dpi=130, facecolor=SURF)


def plot_monthly(m):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8), facecolor=SURF)
    for ax, (col, title, k) in zip(axes, [("sm", "Soil moisture 0–100 cm (vol %)", 100),
                                          ("st", "Topsoil temperature 0–7 cm (°C)", 1)]):
        style(ax)
        for period, color in (("1961–1990", BLUE), ("1996–2025", ORANGE)):
            v = m[f"{col}_{period}"] * k
            ax.plot(m.index, v, color=color, lw=2, marker="o", ms=4)
            # label where the two periods are furthest apart, above the upper line and below the lower one
            gap = (m[f"{col}_1996–2025"] - m[f"{col}_1961–1990"]).abs()
            x = int(gap.idxmax())
            upper = v[x] >= max(m[f"{col}_1961–1990"][x], m[f"{col}_1996–2025"][x]) * k - 1e-9
            ax.annotate(period, (x, v[x]), xytext=(0, 9 if upper else -13), textcoords="offset points",
                        ha="center", fontsize=8.5, color=INK2)
        ax.set_xticks(range(1, 13), list("JFMAMJJASOND"))
        ax.set_xlim(0.6, 12.4)
        ax.set_title(title, loc="left", fontsize=10, color=INK)
    fig.suptitle("Monthly means, 1961–1990 vs 1996–2025", x=0.07, ha="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(HERE / "plot_monthly.png", dpi=130, facecolor=SURF)


def ndvi_link(a):
    fs = pd.read_csv(SEG / "sentinel2" / "field_summary.csv")
    fs = fs[fs.use_for_stats]
    years = range(2019, 2027)
    base = a.loc[BASE[0]:BASE[1], "sm_0_100_gs"].mean()
    rows = [dict(year=y, ndvi_peak_p90_farm_median=fs[f"peak_p90_{y}"].median(),
                 sm_0_100_gs_anom_volpct=(a.sm_0_100_gs.get(y, np.nan) - base) * 100,
                 dry_days_gs=a.dry_days_gs.get(y, np.nan), cwb_gs=a.cwb_gs.get(y, np.nan),
                 complete_year=bool(a.complete.get(y, False))) for y in years]
    n = pd.DataFrame(rows).round(3)
    n.to_csv(HERE / "ndvi_vs_soil.csv", index=False)
    OUT["ndvi_vs_soil"] = n.to_dict("records")
    ok = n.dropna()
    if len(ok) >= 5:
        r = stats.spearmanr(ok.sm_0_100_gs_anom_volpct, ok.ndvi_peak_p90_farm_median)
        OUT["ndvi_soil_spearman"] = dict(rho=round(r.statistic, 2), p=round(r.pvalue, 3), n=len(ok))


if __name__ == "__main__":
    daily, farm, cells = load()
    a, p10 = annual(farm)
    a.round(4).to_csv(HERE / "annual.csv")
    per_cell = pd.concat([annual(g.drop(columns="cell"))[0].assign(cell=c) for c, g in daily.groupby("cell")])
    per_cell.round(4).to_csv(HERE / "annual_by_cell.csv")
    OUT["cells"] = cells.to_dict("records")
    OUT["dry_threshold_sm_0_100"] = round(p10, 4)
    OUT["last_date"] = str(farm.dropna(subset=["soil_moisture_0_to_100cm"]).date.max().date())

    cols = ["sm_0_100_gs", "sm_0_7_gs", "sm_100_255_year", "sm_0_100_gs_min", "dry_days_gs", "st_0_7_year",
            "st_28_100_year", "frost_days_topsoil", "t2m_year", "precip_year", "et0_year",
            "precip_gs", "et0_gs", "cwb_year", "cwb_gs"]
    t = pd.DataFrame([trend(a, c) for c in cols]).round(4)
    t.to_csv(HERE / "trends.csv", index=False)
    OUT["trends"] = t.to_dict("records")
    # trend per cell for the key indicators: do the cells agree?
    OUT["trend_by_cell"] = [dict(cell=c, **{k: round(trend(g, k)["sen_slope_per_decade"], 4) for k in
                                             ("sm_0_100_gs", "dry_days_gs", "st_0_7_year")})
                            for c, g in per_cell.groupby("cell")]

    full = a[a.complete]
    OUT["driest_years_gs"] = full.sm_0_100_gs.nsmallest(10).round(4).to_dict()
    OUT["wettest_years_gs"] = full.sm_0_100_gs.nlargest(5).round(4).to_dict()
    OUT["most_dry_days"] = full.dry_days_gs.nlargest(10).to_dict()
    dec = full.groupby((full.index // 10) * 10)[["sm_0_100_gs", "dry_days_gs", "st_0_7_year", "frost_days_topsoil",
                                                  "cwb_gs", "precip_year", "et0_year"]].mean().round(3)
    dec.to_csv(HERE / "decades.csv")
    OUT["decades"] = dec.reset_index().rename(columns={"year": "decade"}).to_dict("records")
    # dry years per decade: years whose Apr–Sep soil moisture is in the driest 20 % of the full record
    q20 = full.sm_0_100_gs.quantile(0.2)
    OUT["dry_years_per_decade"] = full[full.sm_0_100_gs <= q20].groupby(lambda y: y // 10 * 10).size().to_dict()

    farm["year"], farm["month"] = farm.date.dt.year, farm.date.dt.month
    m = pd.DataFrame({f"{k}_{lo}–{hi}": farm[farm.year.between(lo, hi)].groupby("month")[v].mean()
                      for lo, hi in (BASE, RECENT)
                      for k, v in (("sm", "soil_moisture_0_to_100cm"), ("st", "soil_temperature_0_to_7cm"))})
    m.round(4).to_csv(HERE / "monthly_climate.csv")
    OUT["monthly_sm_change_volpct"] = ((m["sm_1996–2025"] - m["sm_1961–1990"]) * 100).round(2).to_dict()
    OUT["monthly_st_change_c"] = (m["st_1996–2025"] - m["st_1961–1990"]).round(2).to_dict()

    # 2026 so far vs the same days in the baseline
    last = pd.Timestamp(OUT["last_date"])
    ytd = lambda y: farm[(farm.year == y) & (farm.date.dt.dayofyear <= last.dayofyear) & farm.month.isin(GS)]
    OUT["gs_2026_to_date"] = dict(
        sm_0_100=round(ytd(2026).soil_moisture_0_to_100cm.mean(), 4),
        base_same_window=round(np.mean([ytd(y).soil_moisture_0_to_100cm.mean() for y in range(*BASE)]), 4),
        rank_driest_of=int(pd.Series({y: ytd(y).soil_moisture_0_to_100cm.mean() for y in range(1950, 2027)})
                           .rank().loc[2026]), years=77)

    plot_annual(a, p10, len(cells))
    plot_monthly(m)
    ndvi_link(a)
    (HERE / "summary.json").write_text(json.dumps(OUT, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(OUT, indent=1, ensure_ascii=False, default=str))
