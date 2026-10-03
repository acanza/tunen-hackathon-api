# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "numpy", "geopandas", "shapely", "rasterio", "requests", "beautifulsoup4"]
# ///
"""Find data that is repeated across our sources for the LuF Seggerde farm, and check whether the copies agree.

Two kinds of repetition:
  A. The same quantity from two or more sources (e.g. clay from SoilGrids and from the BÜK200 profile).
  B. The same values stored more than once in our own files (e.g. two downloads of the same SoilGrids tiles).

Run from this folder:  uv run overlap.py      (offline: reads only files already in data/)

Outputs (all in this folder):
  texture_by_field.csv     SoilGrids clay/sand/SOC/bulk density vs BÜK200 topsoil class, GÜK200 geology, NIBIS
  elevation_by_field.csv   Copernicus DEM field mean vs Open-Meteo model elevation
  moisture_by_cell.csv     ERA5 soil moisture vs SoilGrids field capacity / wilting point
  file_duplicates.csv      files and columns that hold the same values twice
  summary.json             the numbers quoted in README.md
"""
import importlib.util
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

HERE = Path(__file__).parent
DATA = HERE.parent
SEG = DATA / "seggerde"
OUT = {}

# KA5 texture subclasses: clay % range (standard KA5 table, not delivered by the service)
KA5_CLAY = {
    "Ss": (0, 5), "mSfs": (0, 5), "mSgs": (0, 5), "fSms": (0, 5), "gS": (0, 5), "mS": (0, 5), "fS": (0, 5),
    "Su2": (0, 5), "Sl2": (5, 8), "Sl3": (8, 12), "Sl4": (12, 17), "Slu": (8, 17), "St2": (5, 17),
    "Su3": (0, 8), "Su4": (0, 8), "St3": (17, 25), "Ls2": (17, 25), "Ls3": (17, 25), "Ls4": (17, 25),
    "Lt2": (25, 35), "Lts": (25, 45), "Lu": (17, 30), "Uu": (0, 8), "Us": (0, 8), "Ut2": (8, 12),
    "Ut3": (12, 17), "Ut4": (17, 25), "Uls": (8, 17), "Tu3": (30, 45), "Tu2": (45, 65), "Tu4": (25, 35),
}
# KA5 humus class (% humus) -> SOC g/kg with humus = 1.72 x SOC
KA5_HUMUS = {"h0": (0, 0), "h1": (0, 1), "h2": (1, 2), "h3": (2, 4), "h4": (4, 8), "h5": (8, 15),
             "h6": (15, 30), "h7": (30, 100)}
KA5_SOC = {k: (round(lo / 1.72 * 10, 1), round(hi / 1.72 * 10, 1)) for k, (lo, hi) in KA5_HUMUS.items()}
# KA5 effective packing density classes, g/cm³ (approximate match to bulk density)
KA5_LD = {"Ld1": (0, 1.4), "Ld2": (1.4, 1.6), "Ld3": (1.6, 1.75), "Ld4": (1.75, 1.95), "Ld5": (1.95, 9)}
# Bodenschätzung soil classes: share of "abschlämmbare Teile" (< 0.01 mm), not clay
BS_FINES = {"S": (0, 10), "Sl": (10, 14), "lS": (14, 19), "SL": (19, 24), "sL": (24, 30), "L": (30, 45)}


def in_range(v, rng):
    return bool(rng[0] <= v <= rng[1]) if rng and pd.notna(v) else None


def load_buek_parser():
    spec = importlib.util.spec_from_file_location("buek", DATA / "buek200_eda" / "fetch.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_profile_html


# ------------------------------------------------------------------ A. same quantity, several sources
def buek_topsoil():
    """Dominant reference profile per BÜK200 unit -> topsoil (first mineral horizon) classes."""
    parse = load_buek_parser()
    rows = []
    for p in sorted((SEG / "raw" / "buek200").glob("profile_*.html")):
        unit, profiles = parse(p.read_text(encoding="utf-8"))
        if not profiles:
            continue
        share = lambda pr: float((pr.get("Flächenanteil", "0").split()[0] or 0).replace(",", "."))
        dom = max(profiles, key=share)
        hz = [h for h in dom["horizons"] if h["texture_ka5"]]
        top = next((h for h in hz if float(h["top_dm"] or 0) >= 0), hz[0])
        rows.append(dict(TKLE_NR=int(p.stem.split("_")[1]), buek_profile=dom.get("profile", ""),
                         buek_profile_share=share(dom), buek_n_profiles=len(profiles),
                         buek_top_horizon=top["horizon_symbol"],
                         buek_top_depth_dm=f'{top["top_dm"]}-{top["bottom_dm"]}',
                         buek_texture=top["texture_ka5"], buek_humus=top["humus_class"],
                         buek_ld=top["bulk_density_class"],
                         buek_textures_all_profiles=",".join(sorted({
                             next((h["texture_ka5"] for h in pr["horizons"] if h["texture_ka5"]), "")
                             for pr in profiles}))))
    return pd.DataFrame(rows)


def soilgrids_wide(depths=("0-5cm", "5-15cm", "15-30cm")):
    """Per field: SoilGrids Q0.5, inner 20 m zone where it exists else full field, averaged over 0–30 cm."""
    sg = pd.read_csv(SEG / "soilgrids_fields.csv")
    sg = sg[(sg.stat == "Q0.5") & sg.depth.isin(depths)]
    inner = sg[sg.zone == "inner20m"].set_index(["plotId", "prop", "depth"])["mean"]
    full = sg[sg.zone == "full"].set_index(["plotId", "prop", "depth"])["mean"]
    v = inner.reindex(full.index).fillna(full)
    w = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}
    v = (v * v.index.get_level_values("depth").map(w)).groupby(["plotId", "prop"]).sum() / sum(w[d] for d in depths)
    return v.unstack("prop")


def nibis_fields():
    rows = []
    for layer in ("L816", "L849"):
        for f in sorted((SEG / "raw" / "nibis").glob(f"{layer}_*.json")):
            d = json.loads(f.read_text())
            pid = f.stem.split("_", 1)[1]
            p = d["features"][0]["properties"] if d.get("features") else {}
            rows.append(dict(plotId=pid, layer=layer, **{k: p.get(k) for k in
                             ("BOTYP_KLARTEXT", "GEOTYP", "MHGW", "KLASSENZEICHEN", "BODENZ", "ACKERZ")}))
    df = pd.DataFrame(rows)
    a = df[df.layer == "L816"].set_index("plotId")[["BOTYP_KLARTEXT", "GEOTYP", "MHGW"]]
    b = df[df.layer == "L849"].set_index("plotId")[["KLASSENZEICHEN", "BODENZ", "ACKERZ"]]
    out = a.join(b, how="outer").add_prefix("nibis_")
    out["nibis_queried"] = True
    return out


def texture():
    fields = gpd.read_file(SEG / "clean" / "fields_clean.geojson")[["plotId", "fieldName", "area_geom_ha"]]
    bf = pd.read_csv(SEG / "buek200_fields.csv")
    dom = bf.sort_values("share", ascending=False).drop_duplicates("plotId")
    dom = dom.rename(columns={"share": "buek_share", "Legende": "buek_legend"})
    sgw = soilgrids_wide()
    cov = pd.read_csv(SEG / "field_coverage.csv")[["plotId", "sg_pixels"]]
    gk = pd.read_csv(DATA / "guek200_eda" / "guek200_dominant.csv")[["plotId", "Kuerzel", "T1_PethTxt", "share"]]
    gk = gk.rename(columns={"Kuerzel": "guek_unit", "T1_PethTxt": "guek_lithology", "share": "guek_share"})

    t = (fields.drop(columns="geometry", errors="ignore")
         .merge(cov, on="plotId", how="left")
         .merge(dom[["plotId", "TKLE_NR", "buek_legend", "buek_share"]], on="plotId", how="left")
         .merge(buek_topsoil(), on="TKLE_NR", how="left")
         .merge(sgw[["clay", "sand", "silt", "soc", "bdod", "wv0033", "wv1500"]].add_prefix("sg_"),
                left_on="plotId", right_index=True, how="left")
         .merge(gk, on="plotId", how="left")
         .merge(nibis_fields(), left_on="plotId", right_index=True, how="left"))
    t["nibis_queried"] = t["nibis_queried"].fillna(False).astype(bool)

    t["buek_clay_range"] = t.buek_texture.map(KA5_CLAY)
    t["clay_agrees"] = [in_range(v, r) for v, r in zip(t.sg_clay, t.buek_clay_range)]
    t["buek_soc_range"] = t.buek_humus.map(KA5_SOC)
    t["soc_agrees"] = [in_range(v, r) for v, r in zip(t.sg_soc, t.buek_soc_range)]
    t["buek_ld_range"] = t.buek_ld.map(KA5_LD)
    t["bdod_agrees"] = [in_range(v, r) for v, r in zip(t.sg_bdod, t.buek_ld_range)]
    bs = t.nibis_KLASSENZEICHEN.fillna("").str.extract(r"^([A-Za-z]+?)(?=\d)")[0]
    t["nibis_fines_range"] = bs.map(BS_FINES)
    for c in ("buek_clay_range", "buek_soc_range", "buek_ld_range", "nibis_fines_range"):
        t[c] = t[c].map(lambda r: f"{r[0]}–{r[1]}" if isinstance(r, tuple) else "")
    t = t.round(3)
    t.to_csv(HERE / "texture_by_field.csv", index=False)

    # per BÜK unit: does SoilGrids see a difference between the units?
    by_unit = (t.groupby(["TKLE_NR", "buek_texture", "buek_humus"])
               .agg(fields=("plotId", "size"), ha=("area_geom_ha", "sum"),
                    sg_clay_min=("sg_clay", "min"), sg_clay_med=("sg_clay", "median"), sg_clay_max=("sg_clay", "max"),
                    sg_sand_med=("sg_sand", "median"), sg_soc_med=("sg_soc", "median"),
                    sg_bdod_med=("sg_bdod", "median"), buek_clay=("buek_clay_range", "first"),
                    buek_soc=("buek_soc_range", "first"), buek_ld=("buek_ld", "first"),
                    clay_agree_share=("clay_agrees", "mean"), soc_agree_share=("soc_agrees", "mean"))
               .reset_index().sort_values("ha", ascending=False).round(2))
    OUT["texture_by_buek_unit"] = by_unit.to_dict("records")
    OUT["agreement_all_fields"] = {c: dict(agree=int((t[c] == True).sum()), disagree=int((t[c] == False).sum()))
                                   for c in ("clay_agrees", "soc_agrees", "bdod_agrees")}
    OUT["guek_vs_buek"] = (t.groupby(["guek_unit", "TKLE_NR"]).area_geom_ha.sum().round(1)
                           .reset_index().sort_values("area_geom_ha", ascending=False).to_dict("records"))
    OUT["nibis_fields"] = t[t.nibis_queried][["fieldName", "TKLE_NR", "buek_legend", "buek_texture", "sg_clay",
                                               "sg_sand", "nibis_BOTYP_KLARTEXT", "nibis_KLASSENZEICHEN",
                                               "nibis_fines_range", "nibis_BODENZ", "guek_unit"]].to_dict("records")
    # SoilGrids repeats: fields smaller than a pixel share values with neighbours
    OUT["sg_distinct_clay_values"] = int(t.sg_clay.round(2).nunique())
    OUT["sg_fields_below_one_pixel"] = int((t.sg_pixels < 1).sum())
    return t


def elevation():
    dem = pd.read_csv(SEG / "dem_fields.csv")
    dem = dem[dem.zone == "full"][["plotId", "elev_mean", "elev_min", "elev_max"]]
    om = json.loads((SEG / "raw" / "openmeteo" / "archive_2026-09-03_2026-10-02.json").read_text())
    ids = pd.read_csv(SEG / "openmeteo_fields.csv").plotId  # same order as the request
    e = pd.DataFrame({"plotId": ids, "om_elevation": [x["elevation"] for x in om]})
    t = dem.merge(e, on="plotId")
    t["diff_m"] = (t.om_elevation - t.elev_mean).round(2)
    t["om_within_field_range"] = t.om_elevation.between(t.elev_min - 0.5, t.elev_max + 0.5)
    t.round(2).to_csv(HERE / "elevation_by_field.csv", index=False)
    OUT["elevation"] = dict(fields=len(t), mean_diff=round(t.diff_m.mean(), 2),
                            median_abs_diff=round(t.diff_m.abs().median(), 2), max_abs_diff=round(t.diff_m.abs().max(), 2),
                            p90_abs_diff=round(t.diff_m.abs().quantile(.9), 2),
                            share_within_field_range=round(t.om_within_field_range.mean(), 3),
                            distinct_om_values=int(t.om_elevation.nunique()))
    # EDA sites: DEM point vs Open-Meteo 90 m DEM
    ds = pd.read_csv(DATA / "dem_eda" / "dem_sites.csv")[["label", "lon", "lat", "elev_bilinear_m"]]
    gc = pd.read_csv(DATA / "openmeteo_eda" / "grid_cells.csv")[["req_lon", "req_lat", "elev_dem90_m", "elev_cellmean_m"]]
    s = ds.merge(gc, left_on=["lon", "lat"], right_on=["req_lon", "req_lat"])
    s["diff_dem90"] = (s.elev_dem90_m - s.elev_bilinear_m).round(1)
    OUT["elevation_eda_sites"] = s[["label", "elev_bilinear_m", "elev_dem90_m", "diff_dem90", "elev_cellmean_m"]].to_dict("records")


def moisture(tex):
    om = json.loads((SEG / "raw" / "openmeteo" / "archive_2026-09-03_2026-10-02.json").read_text())
    ids = pd.read_csv(SEG / "openmeteo_fields.csv").plotId
    sg = tex.set_index("plotId")[["sg_wv0033", "sg_wv1500", "area_geom_ha"]]
    rows = []
    for pid, x in zip(ids, om):
        h = pd.DataFrame(x["hourly"])
        for depth in ("0_to_7cm", "7_to_28cm"):
            s = h[f"soil_moisture_{depth}"].dropna() * 100  # vol %
            fc, wp = sg.loc[pid, "sg_wv0033"], sg.loc[pid, "sg_wv1500"]
            rows.append(dict(plotId=pid, cell=f'{x["latitude"]:.2f},{x["longitude"]:.2f}', depth=depth,
                             era5_min=s.min(), era5_median=s.median(), era5_max=s.max(),
                             sg_fc_0_30=fc, sg_wp_0_30=wp, hours=len(s),
                             share_above_fc=(s > fc).mean(), share_below_wp=(s < wp).mean()))
    m = pd.DataFrame(rows)
    cell = (m.groupby(["cell", "depth"])
            .agg(fields=("plotId", "size"), era5_median=("era5_median", "first"), era5_min=("era5_min", "first"),
                 era5_max=("era5_max", "first"), sg_fc_min=("sg_fc_0_30", "min"), sg_fc_max=("sg_fc_0_30", "max"),
                 sg_wp_min=("sg_wp_0_30", "min"), sg_wp_max=("sg_wp_0_30", "max"),
                 share_above_fc=("share_above_fc", "mean"), share_below_wp=("share_below_wp", "mean"))
            .reset_index().round(2))
    cell.to_csv(HERE / "moisture_by_cell.csv", index=False)
    OUT["moisture_by_cell"] = cell.to_dict("records")
    fc = json.loads((SEG / "raw" / "openmeteo" / "forecast_2026-10-03.json").read_text())
    OUT["openmeteo_time_overlap"] = dict(archive=[om[0]["hourly"]["time"][0], om[0]["hourly"]["time"][-1]],
                                         forecast=[fc[0]["hourly"]["time"][0], fc[0]["hourly"]["time"][-1]],
                                         archive_depths=[k for k in om[0]["hourly"] if k != "time"],
                                         forecast_vars=[k for k in fc[0]["hourly"] if k != "time"])
    of = pd.read_csv(SEG / "openmeteo_fields.csv")
    OUT["openmeteo_distinct"] = {c: int(of[c].nunique()) for c in ("sm0_7_mean", "precip_30d_mm", "et0_30d_mm")}


# ------------------------------------------------------------------ B. same values stored twice
def raster_equal(a, b):
    with rasterio.open(a) as ra, rasterio.open(b) as rb:
        x, y = ra.read(1).astype("float64"), rb.read(1).astype("float64")
        same_grid = ra.transform.almost_equals(rb.transform) and x.shape == y.shape
        if not same_grid:
            # WCS resamples each request to its own ~250 m grid: compare b at the centres of a's pixels (nearest)
            rr, cc = np.mgrid[0:x.shape[0], 0:x.shape[1]]
            xs, ys = rasterio.transform.xy(ra.transform, rr.ravel(), cc.ravel())
            rb_, cb_ = rasterio.transform.rowcol(rb.transform, xs, ys)
            rb_, cb_ = np.asarray(rb_), np.asarray(cb_)
            inside = (rb_ >= 0) & (rb_ < y.shape[0]) & (cb_ >= 0) & (cb_ < y.shape[1])
            va = x.ravel()[inside]
            vb = y[rb_[inside], cb_[inside]]
            ok = (va != 0) & (vb != 0)
            d = np.abs(va[ok] - vb[ok])
            if not ok.any():
                return dict(same_grid=False, identical=False, compared=0)
            return dict(same_grid=False, identical=False, shape_a=x.shape, shape_b=y.shape,
                        pixel_a=round(ra.transform.a, 3), pixel_b=round(rb.transform.a, 3), compared=int(ok.sum()),
                        share_equal=float((d == 0).mean()), max_abs_diff=float(d.max()),
                        mean_abs_diff=float(d.mean()))
        ok = ~np.isnan(x) & ~np.isnan(y) & (x != 0) & (y != 0)
        return dict(same_grid=True, identical=bool(np.array_equal(np.nan_to_num(x), np.nan_to_num(y))),
                    max_abs_diff=float(np.abs(x[ok] - y[ok]).max()) if ok.any() else None,
                    nodata_a=int((np.isnan(x) | (x == 0)).sum()), nodata_b=int((np.isnan(y) | (y == 0)).sum()))


def files():
    rows = []
    old, new = SEG / "raw" / "soilgrids", SEG / "soilgrids" / "raw"
    fixed = SEG / "raw" / "soilgrids_fixed"
    names = sorted({p.name for p in old.glob("*.tif")} & {p.name for p in new.glob("*.tif")})
    res = [dict(name=n, **raster_equal(old / n, new / n)) for n in names]
    r = pd.DataFrame(res)
    rows.append(dict(what="SoilGrids WCS tiles, seggerde/raw/soilgrids vs seggerde/soilgrids/raw",
                     copies=2, n=len(r), identical=int(r.get("identical", pd.Series(dtype=bool)).fillna(False).sum()),
                     same_grid=int(r.same_grid.sum()),
                     note=f"{len(list(old.glob('*.tif')))} vs {len(list(new.glob('*.tif')))} files, "
                          "the new folder adds the 'uncertainty' statistic; WCS resampled each pull to a slightly "
                          f"different grid; at matching pixels {r.share_equal.mean():.1%} of values are equal, "
                          f"mean |diff| {r.mean_abs_diff.mean():.2f} raw units"))
    OUT["soilgrids_pulls_by_prop"] = (r.assign(prop=r.name.str.split("_").str[0])
                                      .groupby("prop")[["share_equal", "mean_abs_diff", "max_abs_diff"]]
                                      .mean().round(3).reset_index().to_dict("records"))
    res2 = [dict(name=n, **raster_equal(old / n, fixed / n)) for n in names[:40] if (fixed / n).exists()]
    r2 = pd.DataFrame(res2)
    rows.append(dict(what="SoilGrids raw vs soilgrids_fixed (same tiles, CRS + nodata added)", copies=2, n=len(r2),
                     identical=int(r2.get("identical", pd.Series(dtype=bool)).fillna(False).sum()),
                     same_grid=int(r2.same_grid.sum()) if len(r2) else 0,
                     note="values equal except 0 -> NaN; sample of 40 tiles"))

    src = gpd.read_file(DATA.parent / "LuF-Seggerde-Dev-fields.geojson")
    rows.append(dict(what="LuF-Seggerde-Dev-fields.geojson archived vs active features", copies=2, n=len(src),
                     identical=86, same_grid=None, note="86 of 87 archived features copy an active field (clean/fields_audit.csv)"))
    act = gpd.read_file(SEG / "fields_active.geojson").to_crs(25832).set_index("plotId")
    cln = gpd.read_file(SEG / "clean" / "fields_clean.geojson").to_crs(25832).set_index("plotId")
    common = act.index.intersection(cln.index)
    sym = act.loc[common].geometry.symmetric_difference(cln.loc[common].geometry, align=True).area
    changed = int((sym > 1).sum())
    rows.append(dict(what="fields_active.geojson vs clean/fields_clean.geojson", copies=2, n=len(common),
                     identical=len(common) - changed, same_grid=None,
                     note=f"{changed} fields differ by >1 m² ({sym.sum() / 1e4:.2f} ha in total); "
                          "soilgrids/buek200/dem/openmeteo stats use fields_active, Sentinel-2 uses fields_clean"))

    # derived tables that copy columns from other tables
    cov = pd.read_csv(SEG / "field_coverage.csv")
    dem = pd.read_csv(SEG / "dem_fields.csv")
    m = cov.merge(dem[dem.zone == "full"][["plotId", "elev_mean"]], on="plotId")
    rows.append(dict(what="field_coverage.csv elev_mean_m vs dem_fields.csv elev_mean", copies=2, n=len(m),
                     identical=int((m.elev_mean_m - m.elev_mean).abs().lt(0.051).sum()), same_grid=None,
                     note="field_coverage.csv repeats columns from soilgrids_fields, buek200_fields, dem_fields, openmeteo_fields"))
    gf = pd.read_csv(DATA / "guek200_eda" / "guek200_fields.csv")
    gd = pd.read_csv(DATA / "guek200_eda" / "guek200_dominant.csv")
    rows.append(dict(what="guek200_dominant.csv ⊂ guek200_fields.csv", copies=2, n=len(gd),
                     identical=len(gd.merge(gf, on=["plotId", "Kuerzel", "area_ha"])), same_grid=None,
                     note="farm data stored under guek200_eda/, not seggerde/"))
    sp = pd.read_csv(SEG / "sentinel2" / "field_season_peaks.csv")
    fs = pd.read_csv(SEG / "sentinel2" / "field_summary.csv")
    cv = fs.melt(id_vars="plotId", value_vars=[c for c in fs if c.startswith("cv_20")], var_name="season", value_name="cv")
    cv["season"] = cv.season.str[3:].astype(int)
    mm = sp.merge(cv, on=["plotId", "season"]).dropna(subset=["cv", "peak_cv"])
    rows.append(dict(what="sentinel2 field_summary.csv cv_<year> vs field_season_peaks.csv peak_cv", copies=2,
                     n=len(mm), identical=int((mm.cv - mm.peak_cv).abs().lt(1e-3).sum()), same_grid=None,
                     note="per-season peak statistics repeated in the wide summary"))
    cmp = pd.read_csv(DATA / "openmeteo_eda" / "compare_soilgrids_fc_wp.csv")
    rows.append(dict(what="openmeteo_eda/compare_soilgrids_fc_wp.csv copies SoilGrids wv0033/wv1500", copies=2,
                     n=int(cmp.sg_fc_wv0033.notna().sum()), identical=None, same_grid=None,
                     note="SoilGrids values copied into the Open-Meteo comparison table"))
    f = pd.DataFrame(rows)
    f.to_csv(HERE / "file_duplicates.csv", index=False)
    OUT["file_duplicates"] = f.to_dict("records")


if __name__ == "__main__":
    tex = texture()
    elevation()
    moisture(tex)
    files()
    (HERE / "summary.json").write_text(json.dumps(OUT, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(OUT, indent=1, ensure_ascii=False, default=str))
