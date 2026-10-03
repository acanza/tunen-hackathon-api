# /// script
# requires-python = ">=3.10"
# dependencies = ["geopandas>=1.0", "shapely>=2", "pyproj", "pandas", "numpy"]
# ///
"""Clean the Seggerde field-boundary file into one field layer for all downstream statistics.

Run from anywhere:
    uv run data/seggerde/clean/clean.py

Input  : <repo>/LuF-Seggerde-Dev-fields.geojson   (never modified)
Outputs: next to this script
    fields_clean.geojson  active fields, cleaned, EPSG:4326
    fields_audit.csv      one row per ORIGINAL feature (174): what happened and why
    summary_before_after.csv
Rules are documented in README.md (same folder). All metric work is done in EPSG:25832.
"""
from __future__ import annotations

import re
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.validation import explain_validity

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[2] / "LuF-Seggerde-Dev-fields.geojson"
CRS_M = 25832

# ---- thresholds (see README for justification) ----
DUP_VERTEX_TOL_M = 0.01      # consecutive vertices closer than 1 cm are duplicates
SPIKE_ANGLE_DEG = 2.0        # interior angle below this at a vertex = needle spike, vertex removed
OVERLAP_MIN_M2 = 0.01        # intersections smaller than this are numerical noise (touching edges)
SLIVER_PART_M2 = 100.0       # drop a polygon part < 1 Sentinel-2 pixel (10 m x 10 m), never the largest part
TINY_HA = 0.1                # fields below this are flagged use_for_stats = False
INNER_BUFFER_M = 20.0
AREA_MISMATCH_ABS_HA = 0.1   # flag area_mismatch if |drawn - declared| > 0.1 ha ...
AREA_MISMATCH_REL = 0.05     # ... or > 5 % of declared (and > AREA_MISMATCH_MIN_HA)
AREA_MISMATCH_MIN_HA = 0.01
ARCHIVE_IOU_MATCH = 0.99


# ---------------------------------------------------------------- helpers
def polygonal(geom):
    """Keep only polygonal parts (make_valid can return lines/points in a GeometryCollection)."""
    parts = [p for p in shapely.get_parts(geom) if p.geom_type == "Polygon" and not p.is_empty]
    return shapely.union_all(parts) if parts else shapely.Polygon()


def _ring_coords_clean(coords: np.ndarray) -> tuple[np.ndarray, int]:
    """Remove needle-spike vertices (interior angle < SPIKE_ANGLE_DEG) iteratively. coords = closed ring."""
    pts = coords[:-1].copy()
    removed = 0
    changed = True
    while changed and len(pts) > 3:
        changed = False
        n = len(pts)
        for k in range(n):
            v1 = pts[k - 1] - pts[k]
            v2 = pts[(k + 1) % n] - pts[k]
            d1, d2 = np.linalg.norm(v1), np.linalg.norm(v2)
            if d1 < 1e-9 or d2 < 1e-9:
                continue
            ang = np.degrees(np.arccos(np.clip(v1 @ v2 / (d1 * d2), -1, 1)))
            if ang < SPIKE_ANGLE_DEG:
                pts = np.delete(pts, k, axis=0)
                removed += 1
                changed = True
                break
    return np.vstack([pts, pts[:1]]), removed


def despike(geom):
    out, total = [], 0
    for p in shapely.get_parts(geom):
        ext, r = _ring_coords_clean(np.asarray(p.exterior.coords)[:, :2])
        total += r
        holes = []
        for h in p.interiors:
            hc, r = _ring_coords_clean(np.asarray(h.coords)[:, :2])
            total += r
            holes.append(hc)
        out.append(shapely.Polygon(ext, holes))
    return shapely.union_all(out) if len(out) > 1 else out[0], total


def count_dup_vertices(geom) -> int:
    n = 0
    for p in shapely.get_parts(geom):
        if p.geom_type != "Polygon":
            continue
        for ring in [p.exterior, *p.interiors]:
            c = np.asarray(ring.coords)[:, :2]
            n += int((np.linalg.norm(np.diff(c, axis=0), axis=1) < DUP_VERTEX_TOL_M).sum())
    return n


def strip_prefix(name: str) -> str:
    return re.sub(r"^\d+\s+", "", name).strip()


def overlap_pairs(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    """All pairs (i<j) with intersection area > OVERLAP_MIN_M2. gdf must be metric and valid."""
    rows = []
    tree = gdf.sindex
    for i, gi in zip(gdf.index, gdf.geometry):
        for j in tree.query(gi, predicate="intersects"):
            j = gdf.index[j]
            if j <= i:
                continue
            a = gi.intersection(gdf.geometry[j]).area
            if a > OVERLAP_MIN_M2:
                rows.append((i, j, a))
    return pd.DataFrame(rows, columns=["i", "j", "m2"])


def layer_stats(gdf_m: gpd.GeoDataFrame, label: str) -> dict:
    valid = gdf_m.geometry.is_valid
    g = gdf_m.copy()
    g["geometry"] = [polygonal(shapely.make_valid(x)) for x in g.geometry]
    ov = overlap_pairs(g)
    ga = g.geometry.area / 1e4
    union_ha = shapely.union_all(g.geometry.values).area / 1e4
    return {
        "layer": label,
        "features": len(g),
        "sum_geom_ha": round(ga.sum(), 3),
        "union_geom_ha": round(union_ha, 3),
        "double_counted_ha": round(ga.sum() - union_ha, 3),
        "overlap_pairs": len(ov),
        "overlap_ha": round(ov.m2.sum() / 1e4, 3),
        "invalid": int((~valid).sum()),
        "multipolygon_type": int((gdf_m.geom_type == "MultiPolygon").sum()),
        "parts_total": int(sum(shapely.get_num_geometries(x) for x in g.geometry)),
        "fields_lt_0.1ha": int((ga < TINY_HA).sum()),
        "dup_vertices": int(sum(count_dup_vertices(x) for x in g.geometry)),
    }


# ---------------------------------------------------------------- main
def main() -> None:
    raw = gpd.read_file(SRC)
    assert raw.crs.to_epsg() == 4326, raw.crs
    raw = raw.rename(columns={"area": "area_declared_ha"})
    raw["src_index"] = range(len(raw))
    m = raw.to_crs(CRS_M)
    m["area_geom_orig_ha"] = m.geometry.area / 1e4
    m["valid_orig"] = m.geometry.is_valid
    m["invalid_reason"] = [("" if v else explain_validity(g)) for g, v in zip(m.geometry, m.valid_orig)]
    m["n_parts_orig"] = [shapely.get_num_geometries(g) for g in m.geometry]
    m["n_holes_orig"] = [sum(shapely.get_num_interior_rings(p) for p in shapely.get_parts(g)) for g in m.geometry]

    audit = m[["src_index", "plotId", "fieldName", "isArchived", "area_declared_ha", "subsidyArea",
               "area_geom_orig_ha", "valid_orig", "invalid_reason", "n_parts_orig", "n_holes_orig"]].copy()
    audit["geom_type_orig"] = m.geom_type.values
    audit["declared_eq_subsidy"] = np.isclose(m.area_declared_ha, m.subsidyArea)

    act = m[~m.isArchived].copy()
    arc = m[m.isArchived].copy()
    stats_before_all = layer_stats(m, "input, all 174 features")
    stats_before = layer_stats(act, "input, 87 active features")

    # ---- Rule 1: archived -> map to active by geometry (IoU), then drop
    act_valid = act.copy()
    act_valid["geometry"] = [polygonal(shapely.make_valid(g)) for g in act.geometry]
    amap = {}
    for idx, g in zip(arc.index, arc.geometry):
        g = polygonal(shapely.make_valid(g))
        cand = act_valid.sindex.query(g, predicate="intersects")
        best, best_iou = None, 0.0
        for c in cand:
            h = act_valid.geometry.iloc[c]
            iou = g.intersection(h).area / g.union(h).area
            if iou > best_iou:
                best, best_iou = act_valid.index[c], iou
        amap[idx] = (best, best_iou)
    for idx, (best, iou) in amap.items():
        r = arc.loc[idx]
        if best is not None and iou >= ARCHIVE_IOU_MATCH:
            a = act.loc[best]
            same_name = strip_prefix(r.fieldName) == strip_prefix(a.fieldName)
            same_decl = np.isclose(r.area_declared_ha, a.area_declared_ha)
            action = "dropped: archived copy of active field"
            why = (f"IoU={iou:.5f} with active '{a.fieldName}'; name {'matches' if same_name else 'DIFFERS'} "
                   f"after stripping numeric prefix; declared area {'identical' if same_decl else 'DIFFERS'}")
            audit.loc[audit.src_index == r.src_index, ["action", "reason", "matched_active_plotId", "matched_active_name", "match_iou"]] = \
                [action, why, a.plotId, a.fieldName, round(iou, 6)]
        else:
            nb = act_valid.distance(polygonal(shapely.make_valid(r.geometry))).sort_values()
            why = (f"archived, no active counterpart (best IoU={iou:.3f}); nearest active "
                   f"'{act.loc[nb.index[0], 'fieldName']}' at {nb.iloc[0]:.0f} m; owner to confirm")
            audit.loc[audit.src_index == r.src_index, ["action", "reason", "match_iou"]] = \
                ["dropped: archived, no active counterpart", why, round(iou, 6)]

    # ---- Rule 2: geometry repair on active fields
    flags: dict[int, list[str]] = {i: [] for i in act.index}
    notes: dict[int, list[str]] = {i: [] for i in act.index}
    geoms = {}
    for i, g in zip(act.index, act.geometry):
        a0 = g.area
        if not g.is_valid:
            g = polygonal(shapely.make_valid(g))
            flags[i].append("repaired_invalid")
            notes[i].append(f"make_valid ({act.loc[i, 'invalid_reason']}), polygonal parts kept, "
                            f"area change {(g.area - a0):+.2f} m2")
        nd = count_dup_vertices(g)
        g = shapely.remove_repeated_points(g, DUP_VERTEX_TOL_M)
        if nd:
            flags[i].append("dup_vertices_removed")
            notes[i].append(f"{nd} duplicate consecutive vertices removed")
        a1 = g.area
        g2, nspk = despike(g)
        g2 = polygonal(shapely.make_valid(g2))
        if nspk:
            g = g2
            flags[i].append("spike_removed")
            notes[i].append(f"{nspk} needle vertex(es) with angle < {SPIKE_ANGLE_DEG} deg removed, "
                            f"area change {(g.area - a1):+.2f} m2")
        # Single-part MultiPolygon -> Polygon (geometry type only)
        if g.geom_type == "MultiPolygon" and shapely.get_num_geometries(g) == 1:
            g = shapely.get_geometry(g, 0)
            flags[i].append("multipolygon_to_polygon")
        geoms[i] = g
    act["geometry"] = pd.Series(geoms)

    # ---- Rule 3: overlaps -> cut the overlap out of the larger feature
    act_m = gpd.GeoDataFrame(act, geometry="geometry", crs=CRS_M)
    ov = overlap_pairs(act_m)
    ov_list = []
    for _, r in ov.sort_values("m2", ascending=False).iterrows():
        i, j = int(r.i), int(r.j)
        big, small = (i, j) if act_m.geometry[i].area >= act_m.geometry[j].area else (j, i)
        inter = act_m.geometry[big].intersection(act_m.geometry[small])
        frac_small = inter.area / act_m.geometry[small].area
        ov_list.append({
            "larger": act_m.fieldName[big], "smaller": act_m.fieldName[small],
            "overlap_m2": round(inter.area, 2),
            "share_of_smaller_inside_larger": round(frac_small, 4),
        })
    for _, r in ov.sort_values("m2", ascending=False).iterrows():
        i, j = int(r.i), int(r.j)
        gi, gj = act_m.geometry[i], act_m.geometry[j]
        big, small = (i, j) if gi.area >= gj.area else (j, i)
        inter_m2 = act_m.geometry[big].intersection(act_m.geometry[small]).area
        if inter_m2 <= OVERLAP_MIN_M2:
            continue
        new = polygonal(shapely.make_valid(act_m.geometry[big].difference(act_m.geometry[small])))
        act_m.loc[big, "geometry"] = new
        flags[big].append(f"overlap_cut:{act_m.fieldName[small]}")
        flags[small].append(f"overlaps:{act_m.fieldName[big]}")
        notes[big].append(f"{inter_m2:.1f} m2 shared with '{act_m.fieldName[small]}' removed from this field")
        notes[small].append(f"{inter_m2:.1f} m2 shared with larger '{act_m.fieldName[big]}' kept in this field")

    # ---- Rule 4: drop sliver parts (< SLIVER_PART_M2), never the largest part
    for i in act_m.index:
        g = act_m.geometry[i]
        parts = list(shapely.get_parts(g))
        if len(parts) <= 1:
            continue
        parts.sort(key=lambda p: -p.area)
        keep = [parts[0]] + [p for p in parts[1:] if p.area >= SLIVER_PART_M2]
        dropped = [p.area for p in parts[1:] if p.area < SLIVER_PART_M2]
        if dropped:
            flags[i].append("sliver_parts_removed")
            notes[i].append(f"{len(dropped)} part(s) < {SLIVER_PART_M2:.0f} m2 removed "
                            f"({sum(dropped):.1f} m2 total)")
        act_m.loc[i, "geometry"] = shapely.union_all(keep)

    # ---- metrics + use_for_stats
    act_m["area_geom_ha"] = act_m.geometry.area / 1e4
    act_m["area_diff_ha"] = act_m.area_geom_ha - act_m.area_declared_ha
    act_m["n_parts"] = [shapely.get_num_geometries(g) for g in act_m.geometry]
    inner = act_m.geometry.buffer(-INNER_BUFFER_M)
    act_m["inner20m_area_ha"] = inner.area / 1e4
    act_m["inner10m_area_ha"] = act_m.geometry.buffer(-10.0).area / 1e4
    for i in act_m.index:
        d = act_m.area_geom_orig_ha[i] - act_m.area_declared_ha[i]
        if abs(d) > AREA_MISMATCH_ABS_HA or (abs(d) > AREA_MISMATCH_REL * act_m.area_declared_ha[i]
                                            and abs(d) > AREA_MISMATCH_MIN_HA):
            flags[i].append("area_mismatch")
            notes[i].append(f"drawn {act_m.area_geom_orig_ha[i]:.3f} ha vs declared "
                            f"{act_m.area_declared_ha[i]:.3f} ha ({d:+.3f} ha) before any cut")
        if act_m.area_geom_ha[i] < TINY_HA:
            flags[i].append("tiny")
        if act_m.inner20m_area_ha[i] <= 0:
            flags[i].append("no_inner20m")
        n_holes = sum(shapely.get_num_interior_rings(p) for p in shapely.get_parts(act_m.geometry[i]))
        if n_holes > act_m.n_holes_orig[i]:
            flags[i].append("has_hole_from_cut")
    act_m["use_for_stats"] = (act_m.area_geom_ha >= TINY_HA) & (act_m.inner20m_area_ha > 0)

    # stable representative point: point_on_surface of the 20 m core if it exists, else of the field
    rp = [shapely.point_on_surface(c if (c is not None and not c.is_empty) else g)
          for c, g in zip(inner, act_m.geometry)]
    rp = gpd.GeoSeries(rp, crs=CRS_M).to_crs(4326)
    act_m["rep_lon"] = rp.x.round(6).values
    act_m["rep_lat"] = rp.y.round(6).values
    act_m["flags"] = [";".join(dict.fromkeys(flags[i])) for i in act_m.index]
    act_m["n_vertices"] = shapely.get_num_coordinates(act_m.geometry.values)

    # ---- write clean layer
    cols = ["plotId", "fieldName", "area_declared_ha", "area_geom_ha", "area_diff_ha", "area_geom_orig_ha",
            "n_parts", "use_for_stats", "inner20m_area_ha", "inner10m_area_ha", "flags", "rep_lon", "rep_lat"]
    out = act_m[cols + ["geometry"]].copy()
    for c in ["area_geom_ha", "area_diff_ha", "area_geom_orig_ha", "inner20m_area_ha", "inner10m_area_ha"]:
        out[c] = out[c].round(4)
    out = out.sort_values("fieldName", key=lambda s: s.str.lower()).reset_index(drop=True)
    out_ll = out.to_crs(4326)
    # reprojection can in principle re-introduce invalidity; check and fail loudly
    bad = ~out_ll.geometry.is_valid
    assert not bad.any(), out_ll[bad].fieldName.tolist()
    dst = HERE / "fields_clean.geojson"
    dst.unlink(missing_ok=True)
    out_ll.to_file(dst, driver="GeoJSON", COORDINATE_PRECISION=7)

    # ---- audit
    for i in act_m.index:
        sel = audit.src_index == act_m.src_index[i]
        action = "kept (modified)" if any(f for f in flags[i] if not f.startswith(("overlaps:", "area_mismatch", "tiny", "no_inner20m"))) else "kept"
        audit.loc[sel, "action"] = action
        audit.loc[sel, "reason"] = "active field; " + ("; ".join(notes[i]) if notes[i] else "no geometry change")
        audit.loc[sel, "flags"] = act_m["flags"][i]
        audit.loc[sel, "use_for_stats"] = bool(act_m.use_for_stats[i])
        audit.loc[sel, "area_geom_clean_ha"] = round(act_m.area_geom_ha[i], 4)
    audit["area_geom_orig_ha"] = audit.area_geom_orig_ha.round(4)
    # which active fields have an archived twin
    twins = audit.dropna(subset=["matched_active_plotId"]).groupby("matched_active_plotId").fieldName.apply(list)
    audit["archived_twins"] = audit.plotId.map(lambda p: "|".join(twins.get(p, [])) if p in twins else "")
    audit = audit.sort_values(["isArchived", "fieldName"]).drop(columns=["src_index"])
    audit.to_csv(HERE / "fields_audit.csv", index=False)

    # ---- before/after summary
    after = layer_stats(act_m[["geometry"]].assign(fieldName=act_m.fieldName), "clean, 87 active features")
    summ = pd.DataFrame([stats_before_all, stats_before, after])
    summ["sum_declared_ha"] = [round(raw.area_declared_ha.sum(), 3), round(act.area_declared_ha.sum(), 3),
                               round(act_m.area_declared_ha.sum(), 3)]
    summ["use_for_stats_true"] = ["", "", int(act_m.use_for_stats.sum())]
    summ.to_csv(HERE / "summary_before_after.csv", index=False)
    pd.DataFrame(ov_list).to_csv(HERE / "overlaps_active_input.csv", index=False)

    with pd.option_context("display.width", 250, "display.max_columns", 30):
        print(summ.T)
        print(pd.DataFrame(ov_list))
        print(out[out["flags"] != ""][["fieldName", "area_declared_ha", "area_geom_orig_ha", "area_geom_ha",
                                    "inner20m_area_ha", "use_for_stats", "flags"]].to_string())
        print(audit.action.value_counts())


if __name__ == "__main__":
    main()
