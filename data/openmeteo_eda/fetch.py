# /// script
# requires-python = ">=3.10"
# dependencies = ["requests"]
# ///
"""Fetch Open-Meteo soil data (ERA5-Land archive + DWD ICON forecast) for the test sites.

Run:  uv run fetch.py [--force]   (writes untouched JSON responses to ./raw/)
Free tier: non-commercial only, <10k calls/day, <5k/h, <600/min. A year of hourly data for
8 variables at one location counts as ~26 "API calls" (weighted by weeks and #variables),
so the full archive pull below costs ~250 weighted calls. We sleep between requests anyway.
"""
import json, time, pathlib, requests

OUT = pathlib.Path(__file__).parent / "raw"
OUT.mkdir(exist_ok=True)

SITES = {  # name: (lon, lat)  WGS84
    "Hildesheimer Boerde (loess)": (9.95, 52.22),
    "Lueneburger Heide (sand)":    (10.05, 53.05),
    "Emsland (sand/peat)":         (7.35, 52.75),
    "Wesermarsch (marsh clay)":    (8.40, 53.35),
    "Teufelsmoor (bog)":           (8.90, 53.25),
    "Solling (upland forest)":     (9.55, 51.75),
    "Hannover centre (urban)":     (9.73, 52.37),
    "Hamburg":                     (9.95, 53.55),
}
LATS = ",".join(str(v[1]) for v in SITES.values())
LONS = ",".join(str(v[0]) for v in SITES.values())

ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
FORECAST = "https://api.open-meteo.com/v1/forecast"

ERA5_DEPTHS = ["0_to_7cm", "7_to_28cm", "28_to_100cm", "100_to_255cm"]
ERA5_HOURLY = [f"soil_moisture_{d}" for d in ERA5_DEPTHS] + [f"soil_temperature_{d}" for d in ERA5_DEPTHS]
ICON_HOURLY = ["soil_moisture_0_to_1cm", "soil_moisture_1_to_3cm", "soil_moisture_3_to_9cm",
               "soil_moisture_9_to_27cm", "soil_moisture_27_to_81cm",
               "soil_temperature_0cm", "soil_temperature_6cm", "soil_temperature_18cm", "soil_temperature_54cm"]
DAILY = ["precipitation_sum", "et0_fao_evapotranspiration"]

REQUESTS = {
    # (1) ERA5-Land archive, full year 2025, all 8 sites in ONE multi-location request
    "archive_era5land_2025": (ARCHIVE, {
        "latitude": LATS, "longitude": LONS, "start_date": "2025-01-01", "end_date": "2025-12-31",
        "hourly": ",".join(ERA5_HOURLY), "daily": ",".join(DAILY),
        "models": "era5_land", "timezone": "UTC"}),
    # GOTCHA: models=era5_land returns precipitation/ET0 as all-null (ERA5-Land has no such
    # fields in Open-Meteo). era5_seamless = ERA5-Land grid/soil + ERA5 for missing variables.
    "archive_era5seamless_daily_2025": (ARCHIVE, {
        "latitude": LATS, "longitude": LONS, "start_date": "2025-01-01", "end_date": "2025-12-31",
        "daily": ",".join(DAILY), "models": "era5_seamless", "timezone": "UTC"}),
    # grid-cell diagnostics: same 1 day, different cell selection / no elevation downscaling
    "archive_era5land_cellcheck_nearest": (ARCHIVE, {
        "latitude": LATS, "longitude": LONS, "start_date": "2025-07-01", "end_date": "2025-07-01",
        "hourly": "soil_moisture_0_to_7cm", "models": "era5_land", "timezone": "UTC",
        "cell_selection": "nearest", "elevation": ",".join(["nan"] * len(SITES))}),
    "archive_era5_cellcheck": (ARCHIVE, {  # ERA5 (0.25 deg) for comparison of grid
        "latitude": LATS, "longitude": LONS, "start_date": "2025-07-01", "end_date": "2025-07-01",
        "hourly": "soil_moisture_0_to_7cm", "models": "era5", "timezone": "UTC"}),
    # archive lag probe: last ~3 weeks, era5_land vs best_match (best_match fills with ECMWF IFS)
    "archive_lagprobe_era5land": (ARCHIVE, {
        "latitude": "52.22", "longitude": "9.95",
        "start_date": "2026-09-15", "end_date": "2026-10-03",
        "hourly": "soil_moisture_0_to_7cm", "daily": "precipitation_sum",
        "models": "era5_land", "timezone": "UTC"}),
    "archive_lagprobe_bestmatch": (ARCHIVE, {
        "latitude": "52.22", "longitude": "9.95",
        "start_date": "2026-09-15", "end_date": "2026-10-03",
        "hourly": "soil_moisture_0_to_7cm", "daily": "precipitation_sum",
        "models": "best_match", "timezone": "UTC"}),
    # (2) Forecast: DWD ICON seamless (D2 2.2km -> EU 7km -> Global 13km), 7 days + 7 past days
    "forecast_icon_seamless": (FORECAST, {
        "latitude": LATS, "longitude": LONS, "hourly": ",".join(ICON_HOURLY),
        "daily": ",".join(DAILY), "models": "icon_seamless",
        "forecast_days": 7, "past_days": 7, "timezone": "UTC"}),
    # individual ICON models (multi-model -> variables get suffix _icon_d2 etc.)
    "forecast_icon_models": (FORECAST, {
        "latitude": LATS, "longitude": LONS, "hourly": ",".join(ICON_HOURLY),
        "models": "icon_d2,icon_eu,icon_global", "forecast_days": 7, "timezone": "UTC"}),
    # ERA5-style depth names in the forecast API are served by ECMWF IFS (not ICON)
    "forecast_ecmwf_era5names": (FORECAST, {
        "latitude": LATS, "longitude": LONS, "hourly": ",".join(ERA5_HOURLY),
        "models": "ecmwf_ifs025", "forecast_days": 7, "timezone": "UTC"}),
}


def get(url, params):
    for attempt in range(5):
        r = requests.get(url, params=params, timeout=300)
        if r.status_code == 200:
            return r
        print("  HTTP", r.status_code, r.text[:200], flush=True)
        time.sleep(20 * (attempt + 1))  # 429 -> back off
    r.raise_for_status()


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv  # default: skip requests whose raw file already exists
    logf = OUT / "_requests_log.json"
    log = json.loads(logf.read_text()) if logf.exists() else {}
    for name, (url, params) in REQUESTS.items():
        if (OUT / f"{name}.json").exists() and not force:
            print("skip (exists)", name); continue
        t0 = time.time()
        r = get(url, params)
        dt = time.time() - t0
        (OUT / f"{name}.json").write_text(r.text)
        log[name] = {"url": r.url, "seconds": round(dt, 2), "bytes": len(r.content),
                     "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        print(f"{name}: {len(r.content)/1e6:.2f} MB in {dt:.1f}s", flush=True)
        time.sleep(3)
    logf.write_text(json.dumps(log, indent=1))
