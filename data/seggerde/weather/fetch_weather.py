# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pandas", "numpy"]
# ///
"""Multi-year weather for the Seggerde farm from Open-Meteo (ERA5 archive), 2019 -> latest.

All 87 fields fall in 4 ERA5 cells (../openmeteo_fields.csv), so we request those 4 cell centres
once instead of 87 points. Outputs:
  raw/archive_<start>_<end>.json      untouched response
  daily.csv                           one row per cell x day
  seasons.csv                         one row per cell x year: growing-season indicators
  field_cell.csv                      plotId -> cell
Run from this folder: uv run fetch_weather.py
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).parent
START = "2019-01-01"

DAILY = ["precipitation_sum", "rain_sum", "et0_fao_evapotranspiration", "temperature_2m_mean",
         "temperature_2m_max", "temperature_2m_min", "shortwave_radiation_sum"]
HOURLY = ["soil_moisture_0_to_7cm", "soil_moisture_7_to_28cm", "soil_moisture_28_to_100cm"]


def longest_run(mask):
    best = cur = 0
    for m in mask:
        cur = cur + 1 if m else 0
        best = max(best, cur)
    return best


def main():
    om = pd.read_csv(HERE.parent / "openmeteo_fields.csv")
    om["cell"] = om.era5_cell_lat.round(2).astype(str) + "," + om.era5_cell_lon.round(2).astype(str)
    om[["plotId", "cell"]].to_csv(HERE / "field_cell.csv", index=False)
    cells = om.groupby("cell").agg(lat=("era5_cell_lat", "first"), lon=("era5_cell_lon", "first"),
                                   n_fields=("plotId", "size")).reset_index()
    end = (pd.Timestamp("today").normalize() - pd.Timedelta(days=1)).date()
    raw = HERE / "raw" / f"archive_{START}_{end}.json"
    if not raw.exists():
        raw.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get("https://archive-api.open-meteo.com/v1/archive", timeout=300, params=dict(
            latitude=",".join(map(str, cells.lat)), longitude=",".join(map(str, cells.lon)),
            start_date=START, end_date=end, daily=",".join(DAILY), hourly=",".join(HOURLY),
            models="era5_seamless", timezone="Europe/Berlin"))
        r.raise_for_status()
        raw.write_bytes(r.content)
    resp = json.loads(raw.read_text())
    resp = resp if isinstance(resp, list) else [resp]

    days = []
    for c, r in zip(cells.itertuples(), resp):
        d = pd.DataFrame(r["daily"]); d["time"] = pd.to_datetime(d.time)
        h = pd.DataFrame(r["hourly"]); h["time"] = pd.to_datetime(h.time)
        hd = h.set_index("time").resample("D").mean()  # daily mean soil moisture
        d = d.merge(hd, left_on="time", right_index=True, how="left")
        d.insert(0, "cell", c.cell)
        d.insert(1, "returned_lat", r["latitude"]); d.insert(2, "returned_lon", r["longitude"])
        days.append(d)
    daily = pd.concat(days)
    daily.to_csv(HERE / "daily.csv", index=False)
    last = daily.dropna(subset=["precipitation_sum"]).time.max()
    print(f"daily: {len(daily)} rows, cells {daily.cell.nunique()}, last complete precip day {last.date()}")
    print("null share per variable:", daily[DAILY + HOURLY].isna().mean().round(3).to_dict())

    rows = []
    for (cell, year), d in daily.groupby(["cell", daily.time.dt.year]):
        m = d.time.dt.month
        gs, spring, summer = d[(m >= 3) & (m <= 10)], d[(m >= 4) & (m <= 6)], d[(m >= 5) & (m <= 7)]
        complete = gs.precipitation_sum.notna().all() and len(gs) >= 245
        tmean = gs.temperature_2m_mean
        rows.append(dict(
            cell=cell, year=year, season_complete=complete,
            last_day=d.dropna(subset=["precipitation_sum"]).time.max().date(),
            precip_MarOct_mm=gs.precipitation_sum.sum(min_count=1),
            et0_MarOct_mm=gs.et0_fao_evapotranspiration.sum(min_count=1),
            cwb_MarOct_mm=(gs.precipitation_sum - gs.et0_fao_evapotranspiration).sum(min_count=1),
            precip_AprJun_mm=spring.precipitation_sum.sum(min_count=1),
            cwb_AprJun_mm=(spring.precipitation_sum - spring.et0_fao_evapotranspiration).sum(min_count=1),
            gdd5_MarOct=np.clip(tmean - 5, 0, None).sum(),
            hot_days_tmax30=(gs.temperature_2m_max >= 30).sum(),
            frost_days_AprMay=((m.isin([4, 5])) & (d.temperature_2m_min < 0)).sum(),
            longest_dry_spell_MarOct_d=longest_run((gs.precipitation_sum < 1).tolist()),
            sm7_28_MayJul_mean=summer.soil_moisture_7_to_28cm.mean(),
            sm7_28_MayJul_min=summer.soil_moisture_7_to_28cm.min(),
            sm28_100_MayJul_mean=summer.soil_moisture_28_to_100cm.mean(),
            radiation_MarOct_MJ=gs.shortwave_radiation_sum.sum(min_count=1)))
    seasons = pd.DataFrame(rows).round(3)
    seasons.to_csv(HERE / "seasons.csv", index=False)
    print(seasons.groupby("year").mean(numeric_only=True).round(1).drop(columns=["season_complete"]).to_string())
    spread = seasons.groupby("year")[["precip_MarOct_mm", "cwb_MarOct_mm", "sm7_28_MayJul_mean"]].agg(lambda s: s.max() - s.min())
    print("\nspread between the 4 cells per year:\n", spread.round(3).to_string())


if __name__ == "__main__":
    main()
