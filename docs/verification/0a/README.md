# Unit 0A — First real spatial sample

Status: **complete**. Acceptance date: 2026-10-03 (Europe/Madrid).
Combination: SoilGrids clay mean, 0–5 / 5–15 / 15–30 cm. Dependencies: none.
M0 is complete; M1 and the API remain unimplemented.

## Reproduce

From the repository root, with Python 3.9+ and curl:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-feasibility.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/soilgrids_0a.py --output /tmp/soilgrids-0a-new-run
```

Use a new output directory. Network access to maps.isric.org and files.isric.org
is required. Exit 0 means retrieval and checks passed; exit 1 records a blocker
in report.json. There is no fixture fallback. Exact URLs, UTC timestamps,
durations, response hashes, headers, original TIFFs and compressed original VRT
XML are retained. Hashes refer to uncompressed response bytes. VRTs are parsed
as metadata only: no global tiles are downloaded. The field is stored locally.

## Field provenance

`input/field.geojson` is the unchanged feature at zero-based index 53 of the
hackathon sample LuF-Seggerde-Dev-fields.geojson, linked in project-raw-specs.md.
Its name is Wolfskuhle, ID Hk3aYz9j56wbQD4u3rAC, declared area 20.395 ha.
Its simple polygon spans several native pixels. The source URL and collection
hash are in input/provenance.json. Only this field is retained. No independent
survey validation or LBEG coverage check has been performed. The field has no
separate redistribution license; it remains a supplied project sample.

GeoJSON uses longitude/latitude (EPSG:4326). West/south/east/north bounds:
`[11.045702, 52.344595, 11.054692, 52.348776]`.

## Live evidence

Accepted run: [report.json](live-2026-10-03-r4/report.json).
Eight sequential requests succeeded in 14.997 seconds, downloading 17,846,372
bytes, mostly VRT metadata. Each depth raster is 3 × 3 at **250 m**, with five
valid pixel centers inside the field. No resampling is performed.
Original TIFFs retain the bounding rectangle; report grids apply the polygon
mask, with null outside it or for missing values. Rows run north to south;
columns west to east. Affine transforms and full CRS are recorded per depth.

Top-left retained cell:

| Depth | Raw clay (g/kg) | Clay (%) |
| --- | ---: | ---: |
| 0–5 cm | 192 | 19.2 |
| 5–15 cm | 171 | 17.1 |
| 15–30 cm | 225 | 22.5 |

`(192*5 + 171*10 + 225*15) / 300 = 20.15%`.
The five derived cells range from 17.2667% to 20.15%, with an unweighted cell
mean of 18.72%. This is not a precise area-weighted parcel statistic. Native
cells overlap boundaries; center-based masking is a raster approximation.
Very small fields may contain no pixel centers. Coverage is verified only for
this field and these depths, not other sources or parameters.

## Data decisions and upstream inconsistencies

- Official [layer documentation](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html)
  defines clay in g/kg; divide by 10 for mass percent. The service abstract
  corroborates mass fraction. DescribeCoverage incorrectly labels the generic
  band W.m-2.Sr-1; that label is not used for conversion.
- EPSG:152160 is a provider pseudo-code, not an EPSG registry identifier.
  Use `+proj=igh +datum=WGS84 +units=m +no_defs`, following
  [ISRIC's CRS documentation](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html).
  VRT and WCS describe the native 250 m grid. Datum names differ but normalized
  PROJ parameters are equivalent.
- WCS TIFFs omit CRS and nodata tags. The probe explicitly reads each official
  VRT for Homolosine/WGS84 and nodata -32768. Original TIFFs are therefore not
  self-contained georeferenced deliverables; retain their report. M1 must attach
  this metadata during processing. All nine returned cells per depth have valid
  physical values; a live all-nodata region has not been tested.
- Source metadata is retained: SoilGrids250m 2.0, Code_version v2.0.0,
  Outputs_version RUN10, WoSIS_version Data stream 7, and an abstract referring
  to a March 2020 snapshot. These are model/source descriptors, not a verified
  dataset publication date. That date is null; HTTP and retrieval dates do not
  substitute for it.

## Depth method and limitations

Use `(5*c0_5 + 10*c5_15 + 15*c15_30) / 300` for raw g/kg inputs.
This is the thickness-weighted mean of predicted clay concentrations, assuming
each interval is represented by its supplied mean prediction. It is a derived
depth average, not a new observation, bulk-density-weighted profile composition,
or uncertainty estimate. Require all intervals in every cell; missing depth
produces null without renormalization. This method does not establish a valid
method for pH or percentiles.

## Workload, license and restrictions

Local budgets: eight sequential requests, zero retries, connection timeout 10 s,
request timeout 45 s, 8 MiB per response, 4,096 pixels per depth. Nominal network
ceiling: 360 s / 64 MiB per run. The byte cap accommodates roughly 6 MB VRTs.
These are local budgets, not provider quotas. M1 can retain verified metadata
to reduce repeated transfers; this unit implements no runtime cache.

Capabilities declares access constraints None. The official
[access policy](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html)
licenses SoilGrids under CC BY 4.0. Retain credit to **ISRIC — World Soil
Information**, the SoilGrids source and [license link](https://creativecommons.org/licenses/by/4.0/),
and identify clipping, unit conversion and depth averaging as modifications.
No numeric WCS rate quota was found in the reviewed official documentation;
the REST rate limit is not asserted to apply to WCS. REST was not queried;
the documentation still reports a pause. This live WCS success is not an uptime
guarantee. Protocol reference: [official WCS guide](https://docs.isric.org/globaldata/soilgrids/wcs.html).

## Verification and acceptance record

- Deterministic command: `.venv/bin/python -m unittest discover -s tests -v`.
  Three tests pass: independent conversion/depth calculation and missing interval;
  valid zero and required depths; polygon hole and exterior mask. These synthetic
  test grids are not provider evidence.
- Live command: `.venv/bin/python scripts/soilgrids_0a.py --output docs/verification/0a/live-2026-10-03-r4`.
  Exit 0. All depths downloaded and checked; requests, metadata and values are
  recorded in the accepted report. Python 3.9.6, rasterio 1.4.3, GDAL 3.9.3,
  numpy 2.0.2 on macOS arm64.
- Earlier runs are diagnostic evidence only: live-2026-10-03 rejected absent
  TIFF CRS; r2 enforced the original 2 MiB cap; r3 rejected equivalent CRS
  definitions with different datum names. The accepted run addresses these.
- No earlier application regression suite exists. API, PNG, production clipping,
  cache, refresh, other parameters and LBEG are outside this unit.
- Acceptance: reproducible spatial values, all required depth intervals,
  defensible depth averaging, metadata provenance and bounded retrieval are
  demonstrated. **M0 is complete and 1A is unblocked.** M1 must carry forward the
  documented metadata corrections and its full validation/rendering checks.
