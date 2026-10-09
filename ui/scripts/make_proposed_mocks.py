# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "shapely", "pyproj"]
# ///
"""Mock fixtures for the 🔴 features of poc/UI_BRIEF.md (sampling plan, signals, crop suitability,
discrepancy, productivity rank), in the brief's PROPOSED shapes, for a handful of demo fields.

    uv run ui/scripts/make_proposed_mocks.py      # from the repo root, after export_fixtures.py

These are UI mocks, not data products: the rules below are rough stand-ins so the screens look plausible.
Every file carries "_mock": true and the UI shows a "Preview: mock data" badge. Reads the store read-only.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.ops import transform as shp_transform

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "poc" / "store"
MOCK = ROOT / "ui" / "public" / "mock"
DEMO = ["Bocksenden", "Altenaer Weg", "Cawi-Wiese", "Heuweg", "Mittelbreite", "Sandberg - 2"]
Z90 = 1.645
LIMING_PH = 5.5
TO_UTM = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)
TO_WGS = Transformer.from_crs("EPSG:32632", "EPSG:4326", always_xy=True)


def phi(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1 + np.vectorize(math.erf)(x / math.sqrt(2)))


def layer(entry, p, s):
    return next((l for l in entry["layers"] if l["parameter"] == p and l["source"] == s), None)


def ok(l):
    return l is not None and l["status"] in ("ok", "partial")


def tif(l):
    return STORE / l["geotiff_url"].removeprefix("/static/")


def sampling_plan(entry, geom_wgs):
    ph = layer(entry, "ph", "soilgrids")
    if not ok(ph):
        return None
    with rasterio.open(tif(ph)) as r:
        val, lo, hi = (r.read(i) for i in (1, 2, 3))
        t = r.transform
    sigma = np.maximum((hi - lo) / (2 * Z90), 1e-6)
    p = phi((LIMING_PH - val) / sigma)
    du = 1 - np.abs(2 * p - 1)
    geom = shp_transform(lambda x, y: TO_UTM.transform(x, y), geom_wgs)
    inner = geom.buffer(-20)
    zone = inner if not inner.is_empty and inner.area > 0 else geom
    rows, cols = np.where(np.isfinite(val))
    cand = []
    for r_, c_ in zip(rows, cols):
        x, y = t * (c_ + 0.5, r_ + 0.5)
        if zone.contains(Point(x, y)):
            cand.append((float(du[r_, c_]), x, y, float(val[r_, c_]), float(lo[r_, c_]), float(hi[r_, c_])))
    cand.sort(reverse=True)
    max_pts = 5 if geom.area > 5e4 else 3 if geom.area > 1e4 else 1
    spacing = max(50, round(math.sqrt(geom.area / max_pts) / 2, -1))  # spread points over larger fields
    picked = []
    for c in cand:
        if all(math.hypot(c[1] - q[1], c[2] - q[2]) >= spacing for q in picked):
            picked.append(c)
        if len(picked) == max_pts:
            break
    area_ha = geom.area / 1e4
    points = []
    for i, (d, x, y, v, l_, h_) in enumerate(picked, 1):
        lon, lat = TO_WGS.transform(x, y)
        share = round(area_ha / max(len(picked), 1), 1)
        points.append({
            "rank": i, "lat": round(lat, 6), "lon": round(lon, 6), "decision": "liming", "parameter": "ph",
            "decision_uncertainty": round(d, 2), "current_estimate": round(v, 1), "interval_90": [round(l_, 1), round(h_, 1)],
            "why": (f"pH estimate {v:.1f} with a range of {l_:.1f}–{h_:.1f} straddles the liming threshold ({LIMING_PH}); "
                    f"one sample settles it for ~{share} ha"),
        })
    return {"points": points, "rules": {"min_spacing_m": int(spacing), "edge_buffer_m": 20, "max_points": max_pts}, "covers_ha": round(area_ha, 1)}


def kw(prob):
    if prob is None:
        return "Unknown"
    return "Probable" if prob >= 0.7 else "Possible" if prob >= 0.4 else "Unlikely" if prob >= 0.15 else "No"


def signals(entry):
    ph = layer(entry, "ph", "soilgrids")
    nfk = layer(entry, "nfk", "best")
    tex = layer(entry, "texture", "soilgrids")
    out = []
    if ok(ph):
        m, (lo, hi) = ph["stats"]["mean"], ph["confidence"]["interval_90"]
        sigma = (hi - lo) / (2 * Z90)
        prob = float(phi(np.array([(LIMING_PH - m) / sigma]))[0])
        unknown = ph["confidence"]["level"] == "low" and lo < 4.8 and hi > 7.0
        out.append({"signal": "liming", "keyword": "Unknown" if unknown else kw(prob), "probability": round(prob, 2),
                    "because": ["ph_range_crosses_threshold"] if unknown else ["ph_below_threshold"],
                    "farmer_text": "Public data can't tell whether this field needs lime; a soil sample would settle it." if unknown
                    else "The topsoil may be acid enough to need lime.",
                    "audit": {"inputs": {"ph_soilgrids": m, "ph_interval_90": [lo, hi]}, "rule": "P(pH < 5.5); Unknown if low confidence and range spans 4.8–7.0"}})
    if ok(nfk):
        m = nfk["stats"]["mean"]
        prob = 0.85 if m < 90 else 0.55 if m < 120 else 0.25 if m < 160 else 0.1
        out.append({"signal": "drought_risk", "keyword": kw(prob), "probability": prob,
                    "because": ["nfk_best_below_90_mm" if m < 90 else "nfk_best_mm", "dry_spring_in_3_of_8_seasons"],
                    "farmer_text": "Dry spells are likely to limit this field: it holds little plant-available water." if prob >= 0.7
                    else "Dry springs can limit this field." if prob >= 0.4 else "The soil holds enough water to bridge most dry spells.",
                    "audit": {"inputs": {"nfk_best_mm": round(m), "cwb_apr_jun_dry_mm": -185}, "rule": "nFK < 90 mm → 0.85; < 120 → 0.55; < 160 → 0.25"}})
    sand = tex["stats"].get("sand_mean") if ok(tex) else None
    out.append({"signal": "erosion", "keyword": "Possible" if sand and sand > 60 else "Unlikely", "probability": 0.45 if sand and sand > 60 else 0.2,
                "because": ["flat_terrain", "sandy_topsoil"] if sand and sand > 60 else ["flat_terrain"],
                "farmer_text": "Water erosion is unlikely on this flat land; bare sandy soil can blow in spring winds." if sand and sand > 60
                else "Erosion is unlikely on this flat land.",
                "audit": {"inputs": {"sand_pct": sand, "slope_deg_p90": 1.2}, "rule": "water: slope; wind: sand > 60 %"}})
    out.append({"signal": "compaction", "keyword": "Unknown", "probability": None, "because": ["no_traffic_or_bulk_density_data"],
                "farmer_text": "We have no data on traffic or soil density, so we can't judge compaction.",
                "audit": {"inputs": {}, "rule": "needs bulk density / traffic data"}})
    leach = 0.8 if (sand and sand > 60 and ok(nfk) and nfk["stats"]["mean"] < 140) else 0.45
    out.append({"signal": "nitrate_leaching", "keyword": kw(leach), "probability": leach, "because": ["sandy_texture", "winter_rain_surplus"],
                "farmer_text": "Nitrate can wash out of this sandy soil over winter." if leach >= 0.7 else "Some nitrate can wash out over winter.",
                "audit": {"inputs": {"sand_pct": sand, "nfk_best_mm": round(nfk["stats"]["mean"]) if ok(nfk) else None}, "rule": "sand > 60 % and nFK < 140 mm"}})
    return out


CROPS = ["winter_wheat", "barley", "rye", "rapeseed", "maize", "sugar_beet", "potato", "grassland"]
WATER_NEED = {"winter_wheat": 120, "barley": 100, "rye": 70, "rapeseed": 120, "maize": 130, "sugar_beet": 140, "potato": 80, "grassland": 90}
BZ_NEED = {"winter_wheat": 40, "barley": 30, "rye": 18, "rapeseed": 35, "maize": 30, "sugar_beet": 50, "potato": 25, "grassland": 15}
FACTOR = {"low_available_water": "low available water capacity", "low_fertility": "low soil fertility"}


def crops(entry):
    nfk = layer(entry, "nfk", "best")
    bz = layer(entry, "bodenzahl", "best")
    if not (ok(nfk) and ok(bz)):
        return None
    n, b = nfk["stats"]["mean"], bz["stats"]["mean"]
    conf = "low" if "low" in (nfk["confidence"]["level"], bz["confidence"]["level"]) else "medium"
    out = []
    for c in CROPS:
        lim = []
        if n < WATER_NEED[c]:
            lim.append(("low_available_water", WATER_NEED[c] - n))
        if b < BZ_NEED[c]:
            lim.append(("low_fertility", (BZ_NEED[c] - b) * 3))
        worst = max((d for _, d in lim), default=0)
        rating = "Well adapted" if not lim else "Poorly adapted" if worst > 40 else "With limitations"
        name = c.replace("_", " ").replace("winter ", "").capitalize()
        factors = [f for f, _ in sorted(lim, key=lambda x: -x[1])]
        text = f"{name}: {rating}." + (f" Limiting factor: {FACTOR[factors[0]]} (≈ {round(n)} mm, Bodenzahl {round(b)})." if factors else "")
        out.append({"crop": c, "rating": rating, "limiting_factors": factors, "text": text, "confidence": conf,
                    "inputs": {"nfk_best_mm": round(n), "bodenzahl_best": round(b)}})
    return out


def discrepancy(entry):
    a, b = layer(entry, "nfk", "derived"), layer(entry, "nfk", "soilgrids")
    if not (ok(a) and ok(b)):
        return None
    with rasterio.open(tif(a)) as ra, rasterio.open(tif(b)) as rb:
        va, la, ha = (ra.read(i) for i in (1, 2, 3))
        vb, lb, hb = (rb.read(i) for i in (1, 2, 3))
    sa, sb = (ha - la) / (2 * Z90), (hb - lb) / (2 * Z90)
    z = np.abs(va - vb) / np.sqrt(sa ** 2 + sb ** 2)
    m = np.isfinite(z)
    share = float((z[m] > 1).mean()) if m.any() else 0.0
    return [{"parameter": "nfk", "source": "discrepancy", "status": "ok", "png_url": None,
             "stats": {"share_conflict": round(share, 2), "pairs": ["derived", "soilgrids"]},
             "explanation": f"SoilGrids says ~{round(b['stats']['mean'])} mm here, the soil-profile estimate ~{round(a['stats']['mean'])} mm. "
                            + ("They clearly disagree." if share >= 0.5 else
                               "SoilGrids' range is so wide that this gap isn't a statistically clear conflict: it can't confirm or rule out either value.")}]


def main():
    fc = json.loads((MOCK / "fields.geojson").read_text())
    out_dir = MOCK / "proposed"
    out_dir.mkdir(exist_ok=True)
    for i, name in enumerate(DEMO):
        feat = next(f for f in fc["features"] if f["properties"]["name"] == name)
        pid = feat["properties"]["plotId"]
        entry = json.loads((MOCK / "layers" / f"{pid}.json").read_text())
        doc = {"_mock": True, "plot_id": pid}
        if (plan := sampling_plan(entry, shape(feat["geometry"]))) and plan["points"]:
            doc["sampling_plan"] = plan
        doc["signals"] = signals(entry)
        if c := crops(entry):
            doc["crop_suitability"] = c
        if d := discrepancy(entry):
            doc["discrepancy"] = d
        if feat["properties"]["use_for_stats"]:
            doc["field_summary"] = {"productivity_rank_pct": [72, 41, 58, 35, 64][i % 5], "seasons": 8,
                                    "note": "mock value; crop mix not known, weak signal"}
        (out_dir / f"{pid}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False))
        print(name, pid, sorted(k for k in doc if not k.startswith("_")))


if __name__ == "__main__":
    main()
