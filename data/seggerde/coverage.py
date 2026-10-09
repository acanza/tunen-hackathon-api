# /// script
# requires-python = ">=3.11"
# dependencies = ["pandas", "geopandas"]
# ///
"""Join the per-source outputs of fetch.py into one row per active field: field_coverage.csv."""
from pathlib import Path

import geopandas as gpd
import pandas as pd

HERE = Path(__file__).parent

f = gpd.read_file(HERE / "fields_active.geojson")
out = f[["plotId", "fieldName", "area", "area_calc_ha", "inner_area_ha", "geom_was_invalid"]].copy()

# SoilGrids: 250 m pixels covering each field, share without a prediction
sg = pd.read_csv(HERE / "soilgrids_fields.csv")
tot = sg[sg.stat == "_total_pixel_equiv"].drop_duplicates("plotId").set_index("plotId").valid_pixel_equiv
top = sg[(sg.zone == "full") & (sg.stat == "Q0.5") & (sg.depth == "0-5cm")].pivot(index="plotId", columns="prop", values="mean")
valid = sg[(sg.zone == "full") & (sg.stat == "Q0.5") & (sg.depth == "0-5cm") & (sg.prop == "clay")].set_index("plotId").valid_pixel_equiv
out["sg_pixels"] = out.plotId.map(tot)
out["sg_missing_share"] = (1 - out.plotId.map(valid) / out.sg_pixels).round(3)
out["sg_pixels"] = out.sg_pixels.round(3)
for p in ("clay", "sand", "phh2o", "soc"):
    out[f"sg_{p}_median_0_5cm"] = out.plotId.map(top[p]).round(1)

# BUEK200: point-sampled units
bk = pd.read_csv(HERE / "buek200_fields.csv")
pts = pd.read_csv(HERE / "buek200_points.csv").groupby("plotId").size()
dom = bk.sort_values("share").groupby("plotId").tail(1).set_index("plotId")
out["buek_points"] = out.plotId.map(pts)
out["buek_units"] = out.plotId.map(bk.groupby("plotId").size())
out["buek_dominant"] = out.plotId.map(dom.Legende)
out["buek_dominant_share"] = out.plotId.map(dom.share).round(2)

# DEM
dm = pd.read_csv(HERE / "dem_fields.csv").pivot(index="plotId", columns="zone")
out["dem_pixels"] = out.plotId.map(dm[("dem_pixel_equiv", "full")]).round(1)
out["elev_mean_m"] = out.plotId.map(dm[("elev_mean", "full")]).round(1)
out["slope_p90_full"] = out.plotId.map(dm[("slope_p90", "full")]).round(2)
out["slope_p90_inner20m"] = out.plotId.map(dm[("slope_p90", "inner20m")]).round(2)

# Open-Meteo
om = pd.read_csv(HERE / "openmeteo_fields.csv").set_index("plotId")
out["era5_cell"] = out.plotId.map(om.era5_cell_lat.round(2).astype(str) + "," + om.era5_cell_lon.round(2).astype(str))
out["era5_last_valid"] = out.plotId.map(om.sm0_7_last_valid)

# NIBIS: only the probes we managed (see README)
out["nibis_status"] = "not queried (server timeouts)"
out.loc[out.fieldName == "Nachthude 2", "nibis_status"] = "BK50 polygon returned (22 s), not saved"

out.to_csv(HERE / "field_coverage.csv", index=False)
print(out.drop(columns=["plotId"]).describe(include="all").T[["count", "unique", "top", "mean", "min", "max"]].to_string())
