# /// script
# requires-python = ">=3.10"
# dependencies = ["pandas", "numpy", "matplotlib"]
# ///
"""Flatten raw Open-Meteo JSON -> CSVs, compute site summaries, compare with SoilGrids, plot.
Run: uv run analyze.py   (after uv run fetch.py)"""
import json, math, pathlib
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
SITES = {  # keep in sync with fetch.py
    "Hildesheimer Boerde (loess)": (9.95, 52.22),
    "Lueneburger Heide (sand)":    (10.05, 53.05),
    "Emsland (sand/peat)":         (7.35, 52.75),
    "Wesermarsch (marsh clay)":    (8.40, 53.35),
    "Teufelsmoor (bog)":           (8.90, 53.25),
    "Solling (upland forest)":     (9.55, 51.75),
    "Hannover centre (urban)":     (9.73, 52.37),
    "Hamburg":                     (9.95, 53.55),
}

HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw"
SG_CSV = HERE.parent / "soilgrids_eda" / "soilgrids_sites.csv"
NAMES = list(SITES)
ERA5_DEPTHS = ["0_to_7cm", "7_to_28cm", "28_to_100cm", "100_to_255cm"]
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)


def load(name):
    d = json.loads((RAW / f"{name}.json").read_text())
    return d if isinstance(d, list) else [d]


def hav_km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lon2 - lon1) * p / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(a))


def frame(locs, block):
    out = []
    for name, loc in zip(NAMES, locs):
        df = pd.DataFrame(loc[block]); df.insert(0, "site", name)
        out.append(df)
    df = pd.concat(out, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"])
    return df

# ---------------------------------------------------------------- grid cells
arch = load("archive_era5land_2025")
cells = []
for (name, (lon, lat)), a, n, e5, ic, ec in zip(SITES.items(), arch, load("archive_era5land_cellcheck_nearest"),
                                                load("archive_era5_cellcheck"), load("forecast_icon_seamless"),
                                                load("forecast_ecmwf_era5names")):
    cells.append(dict(site=name, req_lon=lon, req_lat=lat,
        era5land_lat=round(a["latitude"], 4), era5land_lon=round(a["longitude"], 4),
        era5land_dist_km=round(hav_km(lat, lon, a["latitude"], a["longitude"]), 2),
        era5land_nearest_same_cell=(a["latitude"], a["longitude"]) == (n["latitude"], n["longitude"]),
        elev_dem90_m=a["elevation"], elev_cellmean_m=n["elevation"],
        era5_lat=e5["latitude"], era5_lon=e5["longitude"],
        era5_dist_km=round(hav_km(lat, lon, e5["latitude"], e5["longitude"]), 2),
        icon_lat=round(ic["latitude"], 4), icon_lon=round(ic["longitude"], 4),
        icon_dist_km=round(hav_km(lat, lon, ic["latitude"], ic["longitude"]), 2),
        ecmwf_ifs025_lat=ec["latitude"], ecmwf_ifs025_lon=ec["longitude"]))
cells = pd.DataFrame(cells)
cells["era5land_cell_shared_with"] = [", ".join(cells.site[(cells.era5land_lat == r.era5land_lat) & (cells.era5land_lon == r.era5land_lon) & (cells.site != r.site)]) for r in cells.itertuples()]
cells.to_csv(HERE / "grid_cells.csv", index=False)
print(cells.to_string(), "\n")

# ---------------------------------------------------------------- flatten archive
hw = frame(arch, "hourly")
hw.to_csv(HERE / "era5land_2025_hourly_wide.csv", index=False)
hl = hw.melt(id_vars=["site", "time"], var_name="variable")
hl["quantity"] = np.where(hl.variable.str.startswith("soil_moisture"), "soil_moisture", "soil_temperature")
hl["depth_band"] = hl.variable.str.replace("soil_moisture_", "").str.replace("soil_temperature_", "")
hl["unit"] = np.where(hl.quantity == "soil_moisture", "m3/m3", "degC")
hl[["site", "time", "quantity", "depth_band", "value", "unit"]].to_csv(HERE / "era5land_2025_hourly_long.csv.gz", index=False)  # ~43 MB uncompressed

daily = frame(load("archive_era5seamless_daily_2025"), "daily")
# add daily means of soil moisture per depth (UTC days)
dm = hw.set_index("time").groupby("site").resample("D").mean(numeric_only=True).round(4).reset_index()
daily = daily.merge(dm, on=["site", "time"]).rename(columns={"time": "date"})
daily.to_csv(HERE / "era5_2025_daily.csv", index=False)

# ---------------------------------------------------------------- forecast flatten
fc = frame(load("forecast_icon_seamless"), "hourly").rename(columns={"time": "time_utc"})
fc.to_csv(HERE / "forecast_icon_seamless_hourly.csv", index=False)
frame(load("forecast_icon_seamless"), "daily").to_csv(HERE / "forecast_icon_seamless_daily.csv", index=False)
fm = frame(load("forecast_icon_models"), "hourly")
fm.to_csv(HERE / "forecast_icon_models_hourly.csv", index=False)
frame(load("forecast_ecmwf_era5names"), "hourly").to_csv(HERE / "forecast_ecmwf_ifs025_hourly.csv", index=False)
cov = {c: fm.groupby("site")[c].apply(lambda s: s.notna().sum()).iloc[0] for c in fm.columns if c.startswith("soil_moisture_0_to_1cm")}
print("forecast hours with data per ICON model:", cov)
last = {c: fm.loc[fm[c].notna(), "time"].max() for c in cov}
print("last forecast hour per ICON model:", last, "\n")

# ---------------------------------------------------------------- seasonal stats
rows = []
for site, g in hw.groupby("site", sort=False):
    g = g.set_index("time")
    for d in ERA5_DEPTHS:
        s = g[f"soil_moisture_{d}"]; t = g[f"soil_temperature_{d}"]; m = s.resample("MS").mean()
        rows.append(dict(site=site, depth=d, sm_min=s.min(), sm_p05=s.quantile(.05), sm_median=s.median(),
                         sm_p95=s.quantile(.95), sm_max=s.max(), sm_range=s.max() - s.min(),
                         sm_wettest_month=m.idxmax().strftime("%b"), sm_driest_month=m.idxmin().strftime("%b"),
                         st_min=t.min(), st_mean=t.mean(), st_max=t.max()))
stats = pd.DataFrame(rows).round(3)
stats.to_csv(HERE / "summary_soil_moisture_by_site_depth.csv", index=False)
print(stats.to_string(), "\n")

clim = daily.groupby("site", sort=False)[["precipitation_sum", "et0_fao_evapotranspiration"]].sum().round(1)
print("2025 totals (era5_seamless, UTC days):\n", clim, "\n")

# ---------------------------------------------------------------- SoilGrids FC / WP per ERA5 band
sg = pd.read_csv(SG_CSV)
sg = sg[(sg.stat == "Q0.5") & sg.prop.isin(["wv0033", "wv1500"])].copy()
sg["site"] = sg.site.str.replace("ö", "oe").str.replace("ü", "ue")
SGD = {"0-5cm": (0, 5), "5-15cm": (5, 15), "15-30cm": (15, 30), "30-60cm": (30, 60), "60-100cm": (60, 100), "100-200cm": (100, 200)}
BANDS = {"0_to_7cm": (0, 7), "7_to_28cm": (7, 28), "28_to_100cm": (28, 100), "100_to_255cm": (100, 255)}

def band_avg(prof, top, bot):  # thickness-weighted; SoilGrids stops at 200 cm
    w = v = 0.0
    for lab, (t, b) in SGD.items():
        ov = max(0, min(b, bot) - max(t, top))
        if ov and not pd.isna(prof.get(lab)): w += ov; v += ov * prof[lab]
    return v / w if w else np.nan

comp = []
for site, g in hw.groupby("site", sort=False):
    sgs = sg[sg.site == site]
    for d, (t, b) in BANDS.items():
        fcap = band_avg(sgs[sgs.prop == "wv0033"].set_index("depth").value.to_dict(), t, b) / 100
        wp = band_avg(sgs[sgs.prop == "wv1500"].set_index("depth").value.to_dict(), t, b) / 100
        s = g[f"soil_moisture_{d}"]
        comp.append(dict(site=site, depth=d, sg_fc_wv0033=round(fcap, 3), sg_wp_wv1500=round(wp, 3),
                         era5_min=s.min(), era5_median=s.median(), era5_max=s.max(),
                         pct_hours_below_sg_wp=round(100 * (s < wp).mean(), 1) if not np.isnan(wp) else np.nan,
                         pct_hours_above_sg_fc=round(100 * (s > fcap).mean(), 1) if not np.isnan(fcap) else np.nan,
                         median_rel_awc=round((s.median() - wp) / (fcap - wp), 2) if not np.isnan(fcap) else np.nan))
comp = pd.DataFrame(comp)
comp.to_csv(HERE / "compare_soilgrids_fc_wp.csv", index=False)
print(comp.to_string(), "\n")

# ---------------------------------------------------------------- spatial smoothness
top = hw.pivot_table(index="time", columns="site", values="soil_moisture_0_to_7cm")[NAMES].resample("D").mean()
deep = hw.pivot_table(index="time", columns="site", values="soil_moisture_28_to_100cm")[NAMES].resample("D").mean()
print("daily 0-7cm SM correlation between sites:\n", top.corr().round(2).to_string(), "\n")
print("daily 28-100cm SM correlation:\n", deep.corr().round(2).to_string(), "\n")
print("annual mean SM per site (0-7 / 28-100):\n", pd.DataFrame({"0-7": top.mean(), "28-100": deep.mean()}).round(3), "\n")
# distinct max values per site (HTESSEL saturation is a per-soil-texture-class constant)
print("max SM over all depths per site:", hw.groupby("site", sort=False)[[f"soil_moisture_{d}" for d in ERA5_DEPTHS]].max().max(axis=1).round(3).to_dict())

# ---------------------------------------------------------------- plots
COL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # validated categorical slots 1-4 (adjacent)
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
plt.rcParams.update({"font.size": 9, "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2,
                     "ytick.color": INK2, "axes.titlesize": 10, "axes.titlecolor": INK, "figure.facecolor": "#fcfcfb",
                     "axes.facecolor": "#fcfcfb"})

def multiples(var, ylabel, fname, title, ref=False):
    fig, axs = plt.subplots(4, 2, figsize=(12, 12), sharex=True, sharey=True)
    for ax, site in zip(axs.flat, NAMES):
        g = hw[hw.site == site].set_index("time")
        for c, d in zip(COL, ERA5_DEPTHS):
            ax.plot(g.index, g[f"{var}_{d}"], color=c, lw=1.4, label=d.replace("_to_", "–").replace("cm", " cm"))
        if ref:
            r = comp[(comp.site == site) & (comp.depth == "28_to_100cm")].iloc[0]
            if not np.isnan(r.sg_fc_wv0033):
                for v, lab in [(r.sg_fc_wv0033, "SoilGrids FC (28–100 cm)"), (r.sg_wp_wv1500, "SoilGrids WP (28–100 cm)")]:
                    ax.axhline(v, color=INK2, lw=1, ls="--")
                    ax.text(g.index[5], v + .005, lab, color=INK2, fontsize=7)
            else:
                ax.text(.02, .03, "no SoilGrids value at this point", transform=ax.transAxes, color=INK2, fontsize=7)
        c = cells[cells.site == site].iloc[0]
        ax.set_title(f"{site}  (cell {c.era5land_lat:.2f}N {c.era5land_lon:.2f}E)", loc="left")
        ax.grid(color=GRID, lw=.6); ax.set_axisbelow(True)
        for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    for ax in axs[:, 0]: ax.set_ylabel(ylabel)
    axs[0, 0].legend(title="ERA5-Land depth", fontsize=8, title_fontsize=8, frameon=False, ncol=2)
    fig.suptitle(title, x=.01, ha="left", fontsize=12, color=INK)
    fig.autofmt_xdate(); fig.tight_layout(); fig.savefig(HERE / fname, dpi=110); plt.close(fig)

multiples("soil_moisture", "soil moisture (m³/m³)", "plot_soil_moisture_2025.png",
          "ERA5-Land hourly soil moisture 2025 by depth band (Open-Meteo, models=era5_land)", ref=True)
multiples("soil_temperature", "soil temperature (°C)", "plot_soil_temperature_2025.png",
          "ERA5-Land hourly soil temperature 2025 by depth band (Open-Meteo, models=era5_land)")
print("done")
