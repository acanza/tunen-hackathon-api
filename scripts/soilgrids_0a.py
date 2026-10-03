"""Bounded, standalone SoilGrids clay feasibility probe (not an API adapter)."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

import numpy as np
import rasterio
from rasterio.features import bounds, geometry_mask
from rasterio.warp import transform_geom

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "docs/verification/0a/input"
ENDPOINT = "https://maps.isric.org/mapserv"
CRS = "+proj=igh +datum=WGS84 +units=m +no_defs"
WCS_CRS = "http://www.opengis.net/def/crs/EPSG/0/152160"
DEPTHS = ("0-5cm", "5-15cm", "15-30cm")
IDS = [f"clay_{depth}_mean" for depth in DEPTHS]
NS = {"wcs": "http://www.opengis.net/wcs/2.0", "gml": "http://www.opengis.net/gml/3.2"}
MAX_BYTES = 2 * 1024 * 1024
MAX_PIXELS = 4096


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(directory, name, parameters, requests):
    url = ENDPOINT + "?" + urlencode([
        ("map", "/map/clay.map"), ("SERVICE", "WCS"), ("VERSION", "2.0.1"),
        *parameters,
    ])
    entry = {"url": url, "file": name, "retrieved_at": datetime.now(timezone.utc).isoformat()}
    requests.append(entry)
    start = time.monotonic()
    path = directory / name
    result = subprocess.run([
        "curl", "--silent", "--show-error", "--fail", "--proto", "=https",
        "--connect-timeout", "10", "--max-time", "45", "--max-filesize", str(MAX_BYTES),
        "--dump-header", str(directory / (name + ".headers")), "--output", str(path), url,
    ], capture_output=True, text=True, timeout=50)
    entry.update(elapsed_seconds=round(time.monotonic() - start, 3), exit_code=result.returncode)
    if path.exists():
        entry.update(bytes=path.stat().st_size, sha256=sha256(path))
    if result.returncode:
        entry["error"] = result.stderr.strip()
        raise RuntimeError(f"Retrieval failed: {name}: {result.stderr.strip()}")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("Response exceeds byte budget")
    return path


def depth_mean_percent(layers):
    """Thickness mean of predicted clay mass fractions, not soil-mass weighting."""
    stack = np.ma.stack(layers).astype(float)
    if stack.shape[0] != 3:
        raise ValueError("All three depth intervals are required")
    missing = np.ma.getmaskarray(stack).any(axis=0)
    result = (stack.filled(0) * np.array([5, 10, 15])[:, None, None]).sum(axis=0) / 300
    return np.ma.array(result, mask=missing)


def json_grid(array):
    return np.where(np.ma.getmaskarray(array), None, array.data).tolist()


def describe_grid(path):
    descriptions = ET.parse(path).findall("wcs:CoverageDescription", NS)
    if {d.findtext("wcs:CoverageId", namespaces=NS) for d in descriptions} != set(IDS):
        raise ValueError("Missing requested depth descriptions")
    grids = []
    for description in descriptions:
        grid = description.find("gml:domainSet/gml:RectifiedGrid", NS)
        origin = tuple(map(float, grid.findtext("gml:origin/gml:Point/gml:pos", namespaces=NS).split()))
        offsets = [tuple(map(float, node.text.split())) for node in grid.findall("gml:offsetVector", NS)]
        if offsets != [(250.0, 0.0), (0.0, -250.0)]:
            raise ValueError("Unexpected native resolution/orientation")
        envelope = description.find("gml:boundedBy/gml:Envelope", NS)
        if envelope.attrib["srsName"] != WCS_CRS:
            raise ValueError("Unexpected source CRS")
        grids.append(origin)
    if len(set(grids)) != 1:
        raise ValueError("Depth grids are not aligned")
    return grids[0]


def run(directory):
    # Never mix new live evidence with earlier successful artifacts.
    directory.mkdir(parents=True, exist_ok=False)
    start = time.monotonic()
    report = {"unit": "0A", "status": "in_progress", "requests": [],
              "field_sha256": sha256(INPUT / "field.geojson"),
              "budget": {"requests": 5, "concurrency": 1, "retries": 0,
                         "seconds_per_request": 45, "bytes_per_response": MAX_BYTES,
                         "pixels_per_depth": MAX_PIXELS}}
    try:
        feature = json.loads((INPUT / "field.geojson").read_text())
        geometry = transform_geom("EPSG:4326", CRS, feature["geometry"])
        report["field_id"] = feature["properties"]["plotId"]
        report["field_bounds_wsen"] = bounds(feature["geometry"])
        cap = fetch(directory, "capabilities.xml", [("REQUEST", "GetCapabilities")], report["requests"])
        available = {n.text for n in ET.parse(cap).findall(".//wcs:CoverageId", NS)}
        if not set(IDS) <= available:
            raise ValueError("Required clay mean coverages absent")
        description = fetch(directory, "description.xml", [
            ("REQUEST", "DescribeCoverage"), ("COVERAGEID", ",".join(IDS)),
        ], report["requests"])
        ox, oy = describe_grid(description)
        west, south, east, north = bounds(geometry)
        # Snap to native pixel edges; request pixel centers to avoid extra border cells.
        x0, y0 = ox - 125, oy - 125
        left = x0 + math.floor((west - x0) / 250) * 250
        right = x0 + math.ceil((east - x0) / 250) * 250
        bottom = y0 + math.floor((south - y0) / 250) * 250
        top = y0 + math.ceil((north - y0) / 250) * 250
        width, height = int((right - left) / 250), int((top - bottom) / 250)
        if not 0 < width * height <= MAX_PIXELS:
            raise ValueError("Reference field exceeds pixel budget")
        layers, metadata = [], []
        reference = None
        for coverage_id in IDS:
            path = fetch(directory, coverage_id + ".tif", [
                ("REQUEST", "GetCoverage"), ("COVERAGEID", coverage_id),
                ("FORMAT", "GEOTIFF_INT16"), ("SUBSETTINGCRS", WCS_CRS), ("OUTPUTCRS", WCS_CRS),
                ("SUBSET", f"X({left + 125},{right - 125})"),
                ("SUBSET", f"Y({bottom + 125},{top - 125})"),
            ], report["requests"])
            with rasterio.open(path) as dataset:
                if dataset.width * dataset.height > MAX_PIXELS or dataset.count != 1:
                    raise ValueError("Unexpected raster dimensions")
                if dataset.crs != rasterio.crs.CRS.from_string(CRS) or dataset.res != (250, 250):
                    raise ValueError("Unexpected raster CRS/resolution")
                if dataset.nodata is None:
                    raise ValueError("No nodata convention supplied")
                if tuple(dataset.bounds) != (left, bottom, right, top):
                    raise ValueError("Returned raster does not match native requested extent")
                key = (dataset.shape, dataset.transform, dataset.crs)
                if reference is not None and key != reference:
                    raise ValueError("Returned depth grids are not aligned")
                reference = key
                values = dataset.read(1, masked=True)
                outside = geometry_mask([geometry], dataset.shape, dataset.transform, all_touched=False)
                values.mask = np.ma.getmaskarray(values) | outside
                if values.count() == 0:
                    raise ValueError("No valid pixel centers inside reference field")
                if values.min() < 0 or values.max() > 1000:
                    raise ValueError("Clay outside physical g/kg range")
                layers.append(values)
                metadata.append({"coverage_id": coverage_id, "shape": dataset.shape,
                                 "crs_wkt": dataset.crs.to_wkt(), "transform": list(dataset.transform)[:6],
                                 "nodata": dataset.nodata, "dtype": dataset.dtypes[0],
                                 "tags": dataset.tags(), "valid_field_cells": int(values.count()),
                                 "raw_g_kg_grid": json_grid(values)})
        derived = depth_mean_percent(layers)
        if derived.count() == 0:
            raise ValueError("No complete depth profile in the field")
        report.update(status="complete", layers=metadata, source_resolution_m=250,
                      output_resolution_m=250, original_unit="g/kg", output_unit="%",
                      depth_intervals_cm=[[0, 5], [5, 15], [15, 30]],
                      method="(5*c0_5 + 10*c5_15 + 15*c15_30) / 300; raw inputs in g/kg",
                      mask_method="Pixel center inside original polygon, including holes; all depths required",
                      clay_0_30cm_percent_grid=json_grid(derived),
                      dataset_version="SoilGrids250m 2.0 (service title); rolling release",
                      dataset_date=None,
                      summary={"valid_cells": int(derived.count()), "min": float(derived.min()),
                               "max": float(derived.max()), "mean": float(derived.mean())})
    except Exception as error:
        report.update(status="blocked", error=f"{type(error).__name__}: {error}")
    report["elapsed_seconds"] = round(time.monotonic() - start, 3)
    report["environment"] = {"rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__,
                             "numpy": np.__version__}
    save_json(directory / "report.json", report)
    print(json.dumps({"status": report["status"], "report": str(directory / "report.json"),
                      "error": report.get("error")}))
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New evidence directory (must not exist)")
    args = parser.parse_args()
    raise SystemExit(run(args.output))
