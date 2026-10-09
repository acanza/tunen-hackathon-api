# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "pandas", "geopandas"]
# ///
"""Pull daily ERA5 soil moisture, soil temperature and water balance 1950–today for the 4 ERA5-Land cells
that cover the LuF Seggerde farm.

Run from this folder:  uv run fetch.py           (cached chunks in raw/ are reused, so a rate-limited run can resume;
                                                  cells with missing chunks are left out of daily.csv)
                       uv run fetch.py --force   (re-download everything)

Two requests per cell and decade (Open-Meteo archive API, timezone UTC):
  soil    models=era5_land     daily means of soil moisture (4 layers + 0–100 cm) and soil temperature (2 layers)
  water   models=era5_seamless daily precipitation, ET0 (FAO), 2 m mean air temperature
          (era5_land returns null precipitation in the daily API)

Each cell is requested at the representative point of its largest field, so the elevation-downscaled
soil temperature refers to farm height. Soil moisture is not downscaled.

Outputs:
  raw/<kind>_<cell>_<start>_<end>.json   untouched responses
  cells.csv                              the 4 cells: request point, returned grid point, elevation, fields, area
  daily.csv                              cell, date, all variables (one row per cell and day)
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

HERE = Path(__file__).parent
RAW = HERE / "raw"
SEG = HERE.parent
FORCE = "--force" in sys.argv
URL = "https://archive-api.open-meteo.com/v1/archive"
UA = {"User-Agent": "tunen-hackathon-eda/1.0"}

START = date(1950, 1, 1)
END = date.today() - timedelta(days=7)  # archive lags ~5–6 days and returns null, not an error, for newer dates
SOIL = ["soil_moisture_0_to_7cm_mean", "soil_moisture_7_to_28cm_mean", "soil_moisture_28_to_100cm_mean",
        "soil_moisture_100_to_255cm_mean", "soil_moisture_0_to_100cm_mean",
        "soil_temperature_0_to_7cm_mean", "soil_temperature_28_to_100cm_mean"]
WATER = ["precipitation_sum", "et0_fao_evapotranspiration", "temperature_2m_mean"]
KINDS = {"soil": ("era5_land", SOIL), "water": ("era5_seamless", WATER)}


def cells():
    om = pd.read_csv(SEG / "openmeteo_fields.csv")
    f = gpd.read_file(SEG / "clean" / "fields_clean.geojson")[["plotId", "fieldName", "area_geom_ha", "rep_lon", "rep_lat"]]
    f = f.merge(om[["plotId", "era5_cell_lat", "era5_cell_lon"]], on="plotId")
    f["cell"] = f.era5_cell_lat.round(2).astype(str) + "_" + f.era5_cell_lon.round(2).astype(str)
    rep = f.sort_values("area_geom_ha", ascending=False).drop_duplicates("cell")
    agg = f.groupby("cell").agg(fields=("plotId", "size"), area_ha=("area_geom_ha", "sum"))
    return (rep.set_index("cell")[["fieldName", "rep_lon", "rep_lat", "era5_cell_lat", "era5_cell_lon"]]
            .rename(columns={"fieldName": "rep_field"}).join(agg).reset_index())


def chunks():
    y = START.year
    while date(y, 1, 1) <= END:
        a, b = date(y, 1, 1), min(date(y + 9, 12, 31), END)
        yield a, b
        y += 10


class DailyLimit(Exception):
    pass


def get(params, tries=8):
    for i in range(tries):
        try:
            r = requests.get(URL, params=params, timeout=180, headers=UA)
        except requests.RequestException as e:
            print("   network error", e); time.sleep(10 * (i + 1)); continue
        if r.status_code == 200:
            return r.content
        if "Daily API request limit" in r.text:  # the full pull (64 requests, ~76 years x 4 cells) is ~1.1 days of free quota
            raise DailyLimit(r.text[:150])
        wait = 70 if r.status_code == 429 else 10 * (i + 1)
        print(f"   HTTP {r.status_code} {r.text[:150]!r}, waiting {wait} s")
        time.sleep(wait)
    raise RuntimeError("gave up after retries")


def fetch(c):
    for kind, (model, vars_) in KINDS.items():
        for a, b in chunks():
            p = RAW / f"{kind}_{c.cell}_{a}_{b}.json"
            if p.exists() and not FORCE:
                continue
            print(f"  {kind} {c.cell} {a}..{b}")
            body = get(dict(latitude=c.rep_lat, longitude=c.rep_lon, start_date=a, end_date=b,
                            daily=",".join(vars_), models=model, timezone="UTC"))
            p.write_bytes(body)
            time.sleep(3)


def flatten(cs):
    frames, meta = [], []
    missing = {c.cell: [f"{k}_{a}" for k in KINDS for a, b in chunks()
                        if not (RAW / f"{k}_{c.cell}_{a}_{b}.json").exists()] for c in cs.itertuples()}
    missing = {k: v for k, v in missing.items() if v}
    if missing:
        print("SKIPPING incomplete cells (re-run fetch.py later to complete them):", missing)
    cs = cs[~cs.cell.isin(missing)]
    for c in cs.itertuples():
        per_kind = []
        for kind in KINDS:
            parts = []
            for a, b in chunks():
                d = json.loads((RAW / f"{kind}_{c.cell}_{a}_{b}.json").read_text())
                parts.append(pd.DataFrame(d["daily"]))
                if kind == "soil" and a == START:
                    meta.append(dict(cell=c.cell, grid_lat=d["latitude"], grid_lon=d["longitude"], elevation=d["elevation"]))
            per_kind.append(pd.concat(parts).set_index("time"))
        df = per_kind[0].join(per_kind[1], how="outer")
        df.columns = [col.removesuffix("_mean") if col.startswith("soil") else col for col in df.columns]
        frames.append(df.assign(cell=c.cell).reset_index().rename(columns={"time": "date"}))
    daily = pd.concat(frames)[["cell", "date"] + [c.removesuffix("_mean") for c in SOIL] + WATER]
    daily.to_csv(HERE / "daily.csv", index=False)
    cs.merge(pd.DataFrame(meta), on="cell").to_csv(HERE / "cells.csv", index=False)
    print(f"daily.csv: {len(daily)} rows, {daily.date.min()} .. {daily.date.max()}")
    print("null share per column:\n", daily.isna().mean().round(4).to_string())


if __name__ == "__main__":
    RAW.mkdir(parents=True, exist_ok=True)
    cs = cells()
    print(cs.to_string(index=False))
    try:
        for c in cs.itertuples():
            fetch(c)
    except DailyLimit as e:
        print("Open-Meteo daily limit reached, stopping downloads:", e)
    flatten(cs)
