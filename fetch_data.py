#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import time

import requests
import pandas as pd

OUTPUT_DIR = Path(__file__).parent / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

def fetch_soilgrids(lon, lat, properties=None):
    """Fetch data from ISRIC SoilGrids API."""
    if properties is None:
        properties = ["clay", "sand", "silt", "phh2o", "soc", "bdod", "cec", "cfvo", "wv0010", "wv0033", "wv1500"]
    
    results = {}
    for prop in properties:
        for depth in ["0-5cm", "5-15cm", "15-30cm", "30-60cm", "60-100cm", "100-200cm"]:
            for value in ["mean", "q0.05", "q0.5", "q0.95"]:
                try:
                    url = f"https://rest.isric.org/soilgrids/v2.0/properties/query"
                    params = {
                        "lon": lon,
                        "lat": lat,
                        "property": prop,
                        "depth": depth,
                        "value": value
                    }
                    resp = requests.get(url, params=params, timeout=30)
                    if resp.status_code == 200:
                        key = f"{prop}_{depth}_{value}"
                        results[key] = resp.json()
                except Exception as e:
                    print(f"Error fetching {prop} {depth} {value}: {e}")
                time.sleep(0.1)  # Be respectful
    return results

def fetch_openmeteo(lon, lat, start_date="2023-01-01", end_date="2023-12-31"):
    """Fetch data from Open-Meteo API."""
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_moisture_28_to_100cm,soil_moisture_100_to_255cm,soil_temperature_0_to_7cm,precipitation,et0_fao_evapotranspiration",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "Europe/Berlin"
    }
    resp = requests.get(url, params=params, timeout=60)
    resp.raise_for_status()
    return resp.json()

def main():
    parser = argparse.ArgumentParser(description="Fetch soil/agri data from APIs")
    parser.add_argument("--lon", type=float, default=9.95, help="Longitude")
    parser.add_argument("--lat", type=float, default=53.55, help="Latitude")
    parser.add_argument("--sample", action="store_true", help="Fetch small sample for testing")
    args = parser.parse_args()
    
    lon, lat = args.lon, args.lat
    
    # Create output subdirs
    point_dir = OUTPUT_DIR / f"{lon:.3f}_{lat:.3f}"
    point_dir.mkdir(exist_ok=True)
    
    # 1. SoilGrids
    print(f"Fetching SoilGrids data for ({lon}, {lat})...")
    if args.sample:
        soilgrids = fetch_soilgrids(lon, lat, properties=["clay", "phh2o"])
    else:
        soilgrids = fetch_soilgrids(lon, lat)
    with open(point_dir / "soilgrids.json", "w") as f:
        json.dump(soilgrids, f, indent=2)
    print(f"  Saved to {point_dir}/soilgrids.json")
    
    # 2. Open-Meteo
    print(f"Fetching Open-Meteo data for ({lon}, {lat})...")
    if args.sample:
        om = fetch_openmeteo(lon, lat, start_date="2023-01-01", end_date="2023-01-07")
    else:
        om = fetch_openmeteo(lon, lat, start_date="2023-01-01", end_date="2023-12-31")
    with open(point_dir / "openmeteo.json", "w") as f:
        json.dump(om, f, indent=2)
    print(f"  Saved to {point_dir}/openmeteo.json")
    
    print("\nDone!")

if __name__ == "__main__":
    main()
