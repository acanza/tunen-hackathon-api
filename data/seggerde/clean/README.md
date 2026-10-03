# Clean field layer (Seggerde)

**Use `fields_clean.geojson` for every per-field statistic.** It holds the 87 active fields, repaired, with no ground counted twice. Every one of the 174 input features is accounted for in `fields_audit.csv`.

To rebuild: `uv run data/seggerde/clean/clean.py` (run from the repo root; the script is deterministic). The input `LuF-Seggerde-Dev-fields.geojson` is never modified. All areas and buffers are computed in EPSG:25832 (UTM 32N). The output is written in EPSG:4326.

| File | Content |
|---|---|
| `clean.py` | The reproducible cleaning script. Thresholds are constants at the top. |
| `fields_clean.geojson` | 87 active fields, cleaned, EPSG:4326, columns below |
| `fields_audit.csv` | One row per original feature (174): action, reason, flags, the archived→active mapping (`matched_active_*`, `match_iou`, `archived_twins`) |
| `summary_before_after.csv` | The before/after table below, machine-readable |
| `overlaps_active_input.csv` | The 7 overlapping pairs in the input, with the share of the smaller field that lies inside the larger one |

## Columns in `fields_clean.geojson`

| Column | Meaning |
|---|---|
| `plotId`, `fieldName` | Unchanged from the input |
| `area_declared_ha` | The input `area` (identical to `subsidyArea` on all 174 features) |
| `area_geom_orig_ha` | Area of the polygon as drawn in the input (EPSG:25832) |
| `area_geom_ha` | Area of the **cleaned** polygon. This is what statistics cover. |
| `area_diff_ha` | `area_geom_ha − area_declared_ha` (negative for fields that had an overlap cut out, e.g. Lange Wiese −1.42) |
| `n_parts` | Polygon parts after cleaning (1 for every field) |
| `use_for_stats` | `true` if area ≥ 0.1 ha **and** the 20 m inner buffer is not empty |
| `inner20m_area_ha`, `inner10m_area_ha` | Area left after shrinking the field by 20 m / 10 m |
| `flags` | Short codes separated by `;` (see below) |
| `rep_lon`, `rep_lat` | Fixed representative point: `point_on_surface` of the 20 m core (or of the whole field if there is no core), so the point is always inside the field and, where possible, ≥ 20 m from its edge. Use it for point APIs (weather, SoilGrids point queries). |

Flags: `repaired_invalid`, `dup_vertices_removed`, `spike_removed`, `multipolygon_to_polygon`, `overlap_cut:<other>` (this field lost the part it shared with `<other>`), `overlaps:<other>` (this field kept a shared part that was removed from the larger `<other>`), `has_hole_from_cut`, `sliver_parts_removed`, `area_mismatch`, `tiny`, `no_inner20m`.

## Issues found in the input

1. **Archived copies.** There are 87 active and 87 archived features. **86 of the 87 archived features are copies of an active field** (IoU ≥ 0.99999 and identical declared area; the name is the active name with a number in front, e.g. `37 Mittelbreite`). The earlier note in `../README.md` said `14 Parkwiese` and `19 Lange Wiese Schonfläche` "differ". That was a matching artefact: they were matched by largest intersection, which picks the field they sit inside. Matched by IoU, they are exact copies of the active `Parkwiese` and `Lange Wiese Schonfläche`. **Only `Hof` (3.09 ha) has no active counterpart.** It lies 108 m from Lange Wiese and overlaps no active field. Its declared area equals its EPSG:25832 polygon area to 1e-9, so it was computed, not typed in. In the input, all archived features are single-part MultiPolygons (except `Hof`) and all active features are Polygons (except `87 Wiese Schenk 1`). "Half the features are MultiPolygons" is just this storage difference. **No feature has more than one part, and no feature has holes.**
2. **Invalid geometry: 1.** Active `Wolfskuhle (ÖVF)` has a ring self-intersection at E 639402.9 / N 5801802.8 (UTM32). `make_valid` changes its area by < 0.01 m². Its archived twin `35 Wolfskuhle (ÖVF)` (stored as a MultiPolygon) is valid.
3. **Overlaps between active fields: 7 pairs, 1.894 ha counted twice.**

   | Larger | Smaller | Overlap | Share of smaller inside larger |
   |---|---|---|---|
   | Lange Wiese | Lange Wiese Schonfläche | 14 097 m² | **100 %** (fully contained) |
   | Wolfskuhle | Wolfskuhle (ÖVF) | 4 470 m² | 16.6 % |
   | Milchkoppel | Parkwiese | 190 m² | **100 %** |
   | Warberg | Tomatenacker | 116 m² | 0.6 % (edge misfit) |
   | Sandberg | Sandberg - 2 | 56 m² | **100 %** |
   | Umfeld Groß | Umfeld Klein | 8.5 m² | edge misfit |
   | Ackern Viehtrift | Ackern Viehtrift (ÖVF) | 0.1 m² | edge misfit |

   The 3 fully contained cases are sub-areas: a protected strip, a 190 m² patch and a 56 m² patch. The parent field's declared area *includes* them. For example, Lange Wiese is declared at 21.4256 ha and drawn at 21.4158 ha including the Schonfläche. So the farm total double-counts them as well.
4. **Area mismatch.** On 72 of 87 active fields, declared and drawn area agree within 0.01 ha. 7 fields are flagged `area_mismatch` (> 0.1 ha, or > 5 % and > 0.01 ha):

   | Field | Declared | Drawn | Diff | Uniform inset that would explain it |
   |---|---|---|---|---|
   | Wolfskuhle | 20.395 | 24.789 | +4.394 (+21.5 %) | 22.9 m |
   | Kampwiese | 9.655 | 10.861 | +1.205 (+12.5 %) | 7.0 m |
   | Silbersee | 12.668 | 13.701 | +1.034 (+8.2 %) | 5.0 m |
   | Tomatenacker | 1.320 | 1.982 | +0.662 (+50 %) | 10.6 m |
   | Stemmen | 6.181 | 6.710 | +0.530 (+8.6 %) | 4.9 m |
   | Milchkoppel | 26.176 | 26.628 | +0.452 (+1.7 %) | 1.3 m |
   | Lange Wiese Schonfläche | 1.211 | 1.410 | +0.199 (+16 %) | 2.1 m |

   Smaller misfits that were not flagged: Rotten −0.083 ha, vor den Tannen +0.074 ha, Abraham +0.029 ha, and Sandberg - 2 (declared 0.001 ha, drawn 0.0056 ha).

   **Hypotheses tested:**
   - *Holes or extra parts?* No. No feature has holes, and every feature has 1 part.
   - *Declared = drawn minus overlapping sub-fields?* No. The overlaps are 0.447 ha (Wolfskuhle), 0.019 ha (Milchkoppel) and 0.012 ha (Tomatenacker), against mismatches of 4.39, 0.45 and 0.66 ha. Wolfskuhle drawn minus the *whole* ÖVF is 22.09 ha, which still does not equal 20.395. Kampwiese, Silbersee and Stemmen overlap nothing.
   - *A uniform headland or edge strip removed?* No. The inset width that would explain each gap ranges from 1.3 m to 22.9 m (table).
   - *Is the excess equal to some other feature's area?* There was no consistent match.
   - *A projection or method difference?* No. On 72 fields the areas agree, and `Hof` matches EPSG:25832 to 1e-9 ha, so the platform computes area the same way this script does.

   **Clue from the number format:** most declared values have 1–4 decimals (m² precision), so they look typed in from an official document such as the subsidy application. Four have full float precision, which means they were computed by software from *a* geometry: `Hof` and `87 Wiese Schenk 1` (both ≈ their current polygon), plus `Abraham` (1.2063 vs 1.2349 drawn) and `Tomatenacker` (1.3201 vs 1.9819 drawn). For the last two, the area was computed from an *earlier, different* polygon, so **the boundaries have been redrawn since the area was set**. The most plausible reading for the rest: the declared area is the eligible / subsidy area (net of hedges, ditches, tracks, water — note the field names `Silbersee`, `See`). The drawn polygon is a coarser gross outline; Wolfskuhle has only 6 vertices. **This was not verified.** It needs the IACS/InVeKoS reference parcels or imagery.
5. **Vertex problems.** 116 duplicate consecutive vertices (< 1 cm apart) in 14 active fields; Krautstemme alone has 85. There is 1 needle spike: `Specksbreite Brache` has a vertex with an interior angle of 0.1° and a 92 m arm, i.e. an out-and-back line. Two sharp corners were left alone because they are plausible real corners: Wiesenbalken (6.9°, 4.3 m) and Wolfskuhle (ÖVF) (6.1°, 0.1 m). There are no self-touching rings apart from the invalid one. No narrow necks: a 2 m opening removes ≤ 0.3 % of any field except the slivers.
6. **Tiny / narrow fields.** `Sandberg - 2` is 0.0056 ha (declared 0.001) and `Parkwiese` 0.019 ha. Both lie fully inside a bigger field. 7 fields have no area left after a 20 m inner buffer: Sandberg - 2, Parkwiese, Lange Wiese Schonfläche (a strip ≈ 30 m wide), Nachthude 1 (0.47 ha), Eichenkoppel (0.45 ha), Papenberg Brache (0.82 ha) and Lehmkuhle (1.11 ha).
7. **Coordinate precision.** The input has 6 decimals (≈ 0.1 m). That is adequate.
8. **Gaps between neighbours.** 16 field pairs lie within 3 m of each other. Most share an exact edge. Closing all gaps narrower than 6 m finds 17 slivers totalling **0.13 ha** for the whole farm. The largest are 402 m² (Wolfskuhle (ÖVF)–Wasserfurche, ≈ 4.7 m wide, probably a real track or ditch), 301 m² (Pumpmühlensee–See, 0.6 m apart) and 107 m² (Papenberg–Papenberg Brache, 0.04 m apart, 0.3 m wide). All are below one 10 m Sentinel-2 pixel in width, so they were **not snapped**. Snapping would add undeclared ground to fields.

## Rules applied (in order)

| # | Rule | Why |
|---|---|---|
| 1 | Drop all 87 archived features. Map each to its active twin by IoU ≥ 0.99. | 86 are exact copies, so keeping them would double the farm (1773 ha instead of 886 ha). `Hof` has no twin and is dropped too, because it is archived. It is listed in the audit and in the open questions. |
| 2 | `make_valid`, keep polygonal parts only | Repairs Wolfskuhle (ÖVF). Area change < 0.01 m². |
| 3 | Remove consecutive vertices closer than 1 cm | Pure noise. It can break some raster and overlay tools. |
| 4 | Remove needle vertices with an interior angle < 2° (iteratively) | Removes the 92 m out-and-back spike in Specksbreite Brache (+4.7 m²). A 2° threshold leaves the real sharp corners alone. |
| 5 | Single-part MultiPolygon → Polygon | Only `87 Wiese Schenk 1`. This changes the type, not the shape. |
| 6 | **Overlaps: keep both features and cut the shared area out of the larger one** | The small features (Schonfläche, ÖVF, Parkwiese, Sandberg - 2) are separately managed sub-areas: a protected strip, an ecological focus area, and so on. They should not contaminate the yield statistics of the main field. The 3 edge misfits (≤ 116 m²) are digitising noise, and assigning them to the smaller field changes the larger one by < 0.3 %. The default rule held up against the evidence, so it was kept. Lange Wiese loses 1.41 ha and gains a hole; Milchkoppel gains a 190 m² hole. |
| 7 | Drop polygon parts < 100 m² (never the largest part) | 100 m² is one Sentinel-2 pixel. Only one crumb was created, by the Wolfskuhle cut (≈ 0 m²). |
| 8 | Keep `area_declared_ha` and add `area_geom_ha`, `area_diff_ha`, `area_geom_orig_ha`. Flag `area_mismatch` if \|drawn − declared\| > 0.1 ha, or > 5 % and > 0.01 ha. | Neither area is "right". Both are kept, and the gap is visible. |
| 9 | `use_for_stats = area_geom_ha ≥ 0.1 ha AND inner20m_area_ha > 0`. Flag, don't delete. | 0.1 ha is 10 Sentinel-2 pixels and less than one DEM/SoilGrids cell. A 20 m core is needed for edge-free statistics. |

## Before / after

| | Input, all | Input, active | **Clean** |
|---|---|---|---|
| Features | 174 | 87 | **87** |
| Sum of polygon areas (ha) | 1773.01 | 885.39 | **883.50** |
| Union area (ha) | 886.59 | 883.50 | **883.50** |
| Ground counted twice (ha) | 886.42 | 1.894 | **0** |
| Overlapping pairs | 114 | 7 | **0** |
| Invalid geometries | 1 | 1 | **0** |
| MultiPolygon features / total parts | 87 / 174 | 1 / 87 | **0 / 87** |
| Fields < 0.1 ha | 4 | 2 | 2 (flagged) |
| Duplicate vertices | 232 | 116 | **0** |
| Sum declared area (ha) | 1756.07 | 876.93 | 876.93 |
| `use_for_stats = true` | | | **80** |

Writing the output at 7 decimal places (≈ 1 cm) re-creates overlaps of up to 0.3 m² along shared edges. This is negligible: sum of areas minus union is 0.00003 ha.

## How downstream code should use this layer

- **Always read `fields_clean.geojson`, never the raw file.** Join other tables on `plotId`.
- **Per-field statistics** (zonal means from Sentinel-2, DEM, SoilGrids): compute over the cleaned geometry. For values that edges contaminate (NDVI, slope, yield potential), use the field shrunk by 20 m (`geometry.to_crs(25832).buffer(-20)`). `inner20m_area_ha` tells you how much is left.
- **Filter on `use_for_stats`** for farm-level rankings, yield-potential maps and anything that compares fields. The 7 excluded fields are not errors. Keep them in the map, show them greyed out, and report "insufficient area". Lange Wiese Schonfläche, Lehmkuhle and Papenberg Brache are narrow but larger than 0.8 ha. If you need values for them, use the 10 m core (`inner10m_area_ha` > 0 for 4 of the 7: those three plus Eichenkoppel) and mark the result as low confidence.
- **Farm totals:** sum `area_geom_ha` (883.50 ha, no double counting), or `area_declared_ha` (876.93 ha) if you need the declared/subsidy figure. Note that the declared total still double-counts the 3 contained sub-areas.
- **Points:** use `rep_lon` / `rep_lat` for weather and point-soil APIs. These points stay the same between runs.
- Show `area_mismatch` fields to the agronomist with both areas. Per-hectare values on those fields depend on which area is used.

## Open questions for the farm / data owner

1. What does `area` / `subsidyArea` represent: eligible subsidy area (net of landscape elements), cultivated area, or a value typed from an older map? Why are they always identical?
2. Wolfskuhle (+4.4 ha), Kampwiese, Silbersee, Stemmen, Tomatenacker, Milchkoppel: is the drawn boundary the gross outline including non-eligible land? Was it redrawn after the area was set? Tomatenacker's and Abraham's declared areas were computed from a different polygon than the current one.
3. `Lange Wiese Schonfläche` lies fully inside `Lange Wiese`, yet Lange Wiese's declared area includes it. Is the Schonfläche managed differently (unfertilised, unmown)? If not, it should be merged back. The same question applies to `Parkwiese` in Milchkoppel and `Sandberg - 2` in Sandberg.
4. Wolfskuhle (ÖVF): we assume ÖVF = *ökologische Vorrangfläche* (CAP greening ecological focus area). 0.45 ha of it lies inside Wolfskuhle. Is the overlap intended?
5. `Hof` (archived, 3.09 ha, no active counterpart, 108 m from Lange Wiese): is it the farmyard and correctly retired, or a field that is missing from the active set?
6. `87 Wiese Schenk 1` is active but has a numbered name like an archived copy, and it has no archived twin. Is the name correct?
7. `Sandberg - 2` is declared as 0.001 ha (10 m²) but drawn as 56 m². What is it?
