# BGR BÜK200: EDA notes

BÜK200 is the federal soil overview map of Germany at 1:200,000, published by BGR together with the state geological surveys. It has 55 map sheets in the TÜK200 sheet grid and gives one **legend unit** (Legendeneinheit) per polygon. BGR's FISBo portal also has a separate **profile page per legend unit**. That page lists one or more reference profiles with horizon data: depths, KA5 texture, humus, packing density, peat properties and so on.

Our role for it: **fallback outside Niedersachsen**, where LBEG BK50 does not exist.

Everything here was fetched on 2026-10-03 by `fetch.py`. All values come from `raw/`.

## Files

| File | What it is |
|---|---|
| `fetch.py` | Reproducible fetcher and flattener. Run `uv run fetch.py`, `--force` to re-fetch, or `--flatten` to rebuild the CSVs offline. |
| `raw/service.json` | MapServer metadata. |
| `raw/query_L0_sheetindex_<lon>_<lat>.json` | Sheet-index query. |
| `raw/query_L<id>_<sheet>_<lon>_<lat>.json` | Legend-unit polygon query on the sheet layer. |
| `raw/identify_<lon>_<lat>.json` | `/identify` over all layers, kept as a cross-check. |
| `raw/profile_TKLE<nr>_<lon>_<lat>.html` | FISBo profile page (HTML) for the legend unit. |
| `raw/_fetch_log.json` | URL, HTTP status and seconds for every request. |
| `buek200_long.csv` | Everything in long format: `site, lon, lat, layer, attribute, value`. Horizon values use attribute keys like `p<profile>.h<nr>.<field>`. |
| `buek200_horizons.csv` | One row per horizon per reference profile, parsed from the FISBo HTML. |

The 10 test sites are included, plus 3 `EDGE` probes for coverage behaviour: Steinhuder Meer (lake), the North Sea, and the Netherlands.

## Service structure

`https://services.bgr.de/arcgis/rest/services/boden/buek200/MapServer` (ArcGIS 11.5, capabilities `Map,Query,Data`, formats JSON/geoJSON/PBF, native SR 3857, maxRecordCount 2000). It has **no related tables** (`tables: []`, `relationships: []`).

| Layer id | Name | Type | Fields |
|---|---|---|---|
| 0 | Blattschnitt (sheet index) | polygon | `BLATTNUM` sheet no. e.g. `"CC 3918"`, `BLATTNAM` sheet name, `JAHR` year published |
| 1 | Blattübersicht | raster (overview image) | only RGB values, so ignore it |
| 2–56 | One layer per sheet, e.g. `17 = "CC3918 HANNOVER"` | polygon | see below |

The sheet layers relevant to Niedersachsen are 8 Emden, 9 Bremerhaven, 10 Hamburg-West, 11 Hamburg-Ost, 15 Lingen, 16 Bielefeld, 17 Hannover, 18 Braunschweig, 24 Kassel and 25 Goslar. The mapping comes from `layers[].name` in the service JSON: `"CC3918 HANNOVER"` corresponds to BLATTNUM `"CC 3918"` (with a space).

**Sheet-layer fields.** Meanings are from the BGR shapefile ReadMe.

| Field | German alias | English / meaning |
|---|---|---|
| `NRKART` | – | Legend unit number on that sheet. Values above 99 are water or other areas, and we saw `999` for a lake. |
| `TKLE_NR` | – | **Germany-wide legend unit key** = sheet no. × 100 + NRKART, e.g. `391852` is sheet 3918, unit 52. Use this as the ID. |
| `BGL` | – | Bodengroßlandschaft (soil landscape) code, `region.landscape`, e.g. `6.2`. Observed: `13.1` = urban cores, `0.0` = water. The service has no lookup table for BGL. |
| `LEG_TEXT` | Legendentext | Full legend text in German, e.g. "Fast ausschließlich Pseudogley-Tschernoseme aus Löss über tiefem Tonsteinzersatz". `*` marks the dominant components. |
| `Legende` | Legende | Short legend in KA4/KA5 notation: `<nr> <soil types>: <substrate>`, e.g. `52 SS-TT: p-ö//c-(z)t(^t)` |
| `Hinweis` | Hinweis | Hatching flag: anthropogenic overprint (30–70 % sealed), cut-over bog, former tidal-flat surface, or transition to Hortisol. It was null at all our sites. |
| `Profile` | Profile | **URL of the FISBo profile page** for this legend unit. Watch out: the URL contains `&amp;`, so html-unescape it before use. |
| `Shape_Area`, `Shape_Length` | | Polygon area (m²) and perimeter (m). |

**Other services under `/boden`.** There are 34 MapServers, mostly 1:1,000,000 thematic maps such as `nfkwe1000`, `humus1000ob`, `bodeneigenschaften`, and `buek1000de/en`. None of them carries BÜK200 horizon tables.

## Working request recipe

You can do this in 2 calls, or 3 with the profile page. All calls are plain GETs with no key.

```
# 1) which sheet?
GET .../buek200/MapServer/0/query?geometry={lon},{lat}&geometryType=esriGeometryPoint&inSR=4326
    &spatialRel=esriSpatialRelIntersects&outFields=*&returnGeometry=false&f=json
    -> features[0].attributes.BLATTNUM = "CC 3918"  -> layer id 17 (via service layer names)

# 2) legend unit
GET .../buek200/MapServer/17/query?<same params>
    -> features[0].attributes = {NRKART, TKLE_NR, BGL, LEG_TEXT, Legende, Hinweis, Profile, ...}

# 3) horizon data (HTML only)
GET https://fisbo.bgr.de/app/FISBoBGR_Profilanzeige/getProfile.php?KARTE=BUEK200&LEGNR={TKLE_NR}
```

**Single-call alternative.** `/identify` with `layers=all` returns layer 0, layer 1 and the matching sheet layer in one response:

```
GET .../MapServer/identify?geometry={lon},{lat}&geometryType=esriGeometryPoint&sr=4326&layers=all
    &tolerance=0&mapExtent={lon-.01},{lat-.01},{lon+.01},{lat+.01}&imageDisplay=400,400,96
    &returnGeometry=false&f=json
```

`identify` has some gotchas compared with `query`:
* It uses **alias** keys (`Legendentext`) instead of field names (`LEG_TEXT`).
* All values come back as **strings**, with German decimal commas (`"219678796,087664"`).
* Nulls come back as the string `"Null"`.
* `layers=visible` with a country-wide extent drops the sheet layers, because they are scale-dependent (visible only at 1:100k–1:400k). `layers=all` works at any extent.

`/query` returns proper types and `f=geojson` works too, so prefer `/query` for the API.

`f=geojson` returns `{"type":"FeatureCollection","features":[{"properties":{...},"geometry":null}]}`.

## Profile / horizon data per legend unit: yes, reachable

Each sheet feature's `Profile` field links to `getProfile.php?KARTE=BUEK200&LEGNR=<TKLE_NR>`. The page is **HTML only**. `&format=xml` is ignored, and the app directory returns 403. `fetch.py:parse_profile_html` parses it.

The page shows a "preliminary data" disclaimer, then one block per reference profile (`Profil: i (von n)`). Each block contains:
* **Bodensystematische Einheit**: KA5 soil type, e.g. `SS-TT`
* **Flächenanteil**: share of the legend unit in %
* **Landnutzung**: CORINE land-use class the profile is representative for

The horizon table under each profile has 18 columns. `buek200_horizons.csv` uses these names:

| CSV column | German header | Meaning |
|---|---|---|
| `nr` | Nr | Horizon number from the top |
| `horizon_symbol` | Symbol | KA5 horizon symbol (Ap, Bv, Sd, hHr …) |
| `top_dm`, `bottom_dm` | Ober-/Untergrenze [dm] | Depth in **decimetres**. Organic layers are negative. Profiles go down to 20 dm (2 m). |
| `stratigraphy` | Stratigraphie | qh = Holocene, qw = Weichselian, qD = Drenthe (Saalian), qp = Pleistocene, … |
| `origin` | Herkunft | Substrate composition and origin, e.g. Lo = loess, Hh = raised-bog peat |
| `geogenesis` | Geogenese | Genesis code, e.g. p, a, fg, f, pfl, og, mp |
| `coarse_fraction` | Grobboden Fraktion | Coarse-fragment type (G, X, Gr, O) |
| `coarse_content_class` | Grobboden Summe | KA5 coarse-fragment content class (0 = none) |
| `texture_ka5` | Bodenart | **KA5 texture subclass**, e.g. Ut3 = medium clayey silt, Tu4 = strongly silty clay, mSfs = fine-sandy medium sand, Ls3 = medium sandy loam, Sl4 = strongly loamy sand |
| `humus_class` | Humus | KA5 humus class: h0 none, h1 <1 %, h2 1–2 %, h3 2–4 %, h4 4–8 %, h5 8–15 %, h6 15–30 %, h7 >30 % (peat) |
| `carbonate_class` | Carbonatgehalt | **Empty in all 225 horizons we fetched** |
| `structure` | Gefüge | **Empty in all 225 horizons** |
| `bulk_density_class` | Trockenrohdichte / eff. Lagerungsdichte | Ld1–Ld5 effective packing density (or Rt) |
| `peat_type`, `peat_decomposition`, `peat_substance_volume` | Torfarten / Zersetzungsstufe / Substanzvolumen | Peat horizons only, e.g. Hh, `k.A.` (= no data), SV3 |
| `acidity_class` | Bodenacidität | KA5 acidity class s1–s6. Mostly empty (filled in 15 of 225 horizons). |

The class meanings above are standard KA5. They are not documented by the service itself, so check them against KA5 before exposing them to users.

**Where there are no profiles.** Urban-core units (Hannover 391893, Hamburg 311870) and water (391800) return a short page that says "keine Profildaten hinterlegt", i.e. no profile data stored. `n_profiles = 0`, and the text is saved under `attribute=note`.

**Bulk alternative.** BGR's per-sheet shapefile downloads (`https://download.bgr.de/bgr/Boden/BUEK200/<sheet>/shp/buek200_<sheet>.zip`, about 10 MB each) contain only the same polygon attributes. According to their ReadMe, the "vorläufige Sachdatenbank" (preliminary attribute database) with lead and companion soils is offered via `https://produktcenter.bgr.de`. We did not find an open bulk download of it. For our API, per-unit scraping of FISBo with caching is the practical route, and there are only about 55 × 100 units in total.

## Coverage behaviour

| Case | Result |
|---|---|
| Normal land | 1 polygon on 1 sheet layer, plus a profile page with 1–10 profiles |
| Urban core (Hannover, Hamburg) | A valid polygon with `BGL 13.1` and `LEG_TEXT` "Böden der Stadtkernbereiche … >70 % versiegelt" (urban-core soils, >70 % sealed). There are **no profiles**. |
| Lake (Steinhuder Meer 9.32, 52.46) | `NRKART 999`, `TKLE_NR 391800`, `BGL 0.0`, `LEG_TEXT "Gewässerflächen"` (water bodies). No profiles. |
| North Sea (7.5, 54.0) | Sheet index hits CC2310 Helgoland, but the sheet layer returns **0 features** |
| Netherlands (6.3, 52.5) | Sheet index hits CC3902 Lingen (the sheet frame extends abroad), but the sheet layer returns **0 features** |

So "no data" shows up as an empty `features` list, not as an error. A point that is completely off the sheet grid also gives an empty sheet-index result.

## Latency

Measured sequentially from `raw/_fetch_log.json`. There were 51 requests (including the service metadata call), all HTTP 200, with no retries needed.

| Request | n | min | median | max (s) |
|---|---|---|---|---|
| Layer-0 query | 13 | 0.24 | 0.27 | 0.30 |
| Sheet-layer query | 13 | 0.30 | 0.38 | 0.50 |
| identify (all layers) | 13 | 0.30 | 0.55 | 0.69 |
| FISBo profile page | 11 | 0.25 | 0.32 | 0.39 |

A full lookup takes about 1 s with 3 sequential calls. Legend-unit and profile results can be cached forever by `TKLE_NR`.

## Key values per site

The dominant profile is profile 1 as listed. Depths are in dm, and the format is texture/humus per horizon.

| Site | Sheet (layer) | TKLE_NR | BGL | Legend (short) | #prof | Profile 1: type, share, horizons |
|---|---|---|---|---|---|---|
| Hildesheimer Börde 9.95, 52.22 | CC3918 (17) | 391852 | 6.2 | `SS-TT: p-ö//c-(z)t(^t)`: Pseudogley-Tschernosem from loess over deep claystone residuum | 1 | SS-TT 95 %: Ap 0–3 Ut3 h3 / Axh 3–5 Ut3 h2 / Sw 5–15 Ut3 h0 / Sd 15–20 Tu2 |
| Hildesheim edge 9.95, 52.12 | CC3918 (17) | 391888 | 7.3 | `LLn, SS-LL …`: Luvisols / stagnic Luvisols from loess over solifluction deposits | 10 | LLn 20 %: Ap 0–3 Ut3 h3 / Al 3–5 Ut3 / Sw-Bt 5–10 Ut4 / Sw-lCv 10–13 Ut3 / Sd 13–20 Ls3 |
| Lüneburger Heide 10.05, 53.05 | CC3126 (11) | 312666 | 4.3 | `BB-PP, PPn: p-s,a-s/fg-s`: podzols from cover/aeolian sand over meltwater sand | 8 | BB-PP 20 %: Aep 0–3 mSfs h2 / Bhs 3–4.1 / Bv 4.1–7 / lCv 7–20 mSfs |
| Emsland 7.35, 52.75 | CC3910 (16) | 391031 | 4.5 | `BB-PP, GG-PP, PPn: p-(k)s,a-s//f-s`: (gleyic) podzols from sand | 8 | BB-PP 20 %: O/Oh −0.7–0 h7 / Aeh 0–1 mSfs h2 / … / lCv 7–20 mSfs |
| Wesermarsch 8.40, 53.35 | CC3110 (9) | 311009 | 1.4 | `MCf, MNf: mp-u,t`: calcareous and clay marsh from silt to clay | 5 | MCf 40 %: Ap 0–2.5 Ut4 h3 / eGo 2.5–7.9 Ut4 / zGro … zGr 7.9–20 Tu4 |
| Teufelsmoor 8.90, 53.25 | CC3118 (10) | 311868 | 4.5 | `HHn: og-Hh; …; HH-YU …`: raised bog, partly deep-ploughed | 7 | HHn 40 %: hHv/hHr/hHw 0–20 Hh peat h7 |
| Solling 9.55, 51.75 | CC4718 (24) | 471851 | 9.1 | `BBn, PP-BB, SS-BB: p-ö/pfl-sn(^s,^u)`: Cambisols from loess over sandstone/siltstone solifluction | 4 | BBn 60 %: O −0.5–0 / Ah 0–0.7 Ls2 h4 / Bv 0.7–5.5 Ls3 / lCv 5.5–12 Sl3 / mCn 12–20 (rock) |
| Hannover centre 9.73, 52.37 | CC3918 (17) | 391893 | 13.1 | "Böden der Stadtkernbereiche" (urban core, >70 % sealed) | **0** | – |
| Farmland (SG null) 10.10, 52.18 | CC3926 (18) | 392650 | 6.2 | `SS-TT: p-ö/g-cl`: Pseudogley-Tschernosem from loess over glacial till | 1 | SS-TT 95 %: Ap 0–3 Ut3 h3 / Axh 3–5 Ut3 h2 / Sw 5–10 Ut3 / Sd 10–20 Sl4 |
| Hamburg 9.95, 53.55 | CC3118 (10) | 311870 | 13.1 | "Böden der Stadtkernbereiche" (urban core) | **0** | – |

Soil-type codes (KA5) used above:
* TT = Tschernosem (Chernozem)
* SS = Pseudogley (Stagnosol)
* LL = Parabraunerde (Luvisol)
* BB = Braunerde (Cambisol)
* PP = Podsol
* GG = Gley
* MC = Kalkmarsch (calcareous marsh)
* MN = Kleimarsch (clay marsh)
* HH = Hochmoor (raised bog)
* HN = Niedermoor (fen)
* RZ = Pararendzina
* YK = Kolluvisol
* YU = deep-ploughed soil (Tiefumbruchboden)

`X-Y` means "X-ish Y", e.g. SS-TT is a stagnic Chernozem. A trailing `n` means the normal subtype.

The two "SoilGrids null" sites (Hildesheim edge and Farmland 10.10, 52.18) both get full BÜK200 answers with horizons.

## Gotchas

1. **The sheet tiling leaks into the API.** There are 55 sheet layers. You must first find the sheet (layer 0 or `identify layers=all`) and then query that sheet's layer. Don't hard-code a single layer id.
2. **`Profile` URL is HTML-escaped** (`&amp;`), so unescape it.
3. **The profile data is HTML only**, flagged by BGR as *preliminary* and given without warranty. A scraper can break if the page layout changes. The parser keys on `th.profil` and on `tr[onmouseover*=mouseOver]` rows, with 18 columns after dropping the `rowspan` graphic cell.
4. **Several profiles per unit.** They are split by soil type *and* land use (CORINE). The same type can appear twice with different land use, e.g. the Lüneburger Heide BB-PP rows for arable vs. forest. `Flächenanteil` does **not always sum to 100 %**: 110 % at Hildesheim edge, 105 % at Solling, 95 % at Wesermarsch. Treat it as indicative weights, not exact shares.
5. **Depths are in dm** and measured from the top of the mineral soil, so organic layers are negative. Values are KA5 *classes*, not numbers: there is no % clay or SOC value. Converting to numbers needs KA5 lookup tables, e.g. texture class to sand/silt/clay midpoints, or humus class to SOC range.
6. Carbonate and structure columns were **empty for every horizon** at our sites, including the Kalkmarsch (calcareous marsh). Don't report "carbonate-free" from an empty cell.
7. `identify` returns strings with decimal commas and `"Null"`. Use `/query` instead.
8. Scale: at 1:200k the polygons are several km wide. The two Hildesheim test points 10 km apart fall into different units, but within a unit everything is constant.
9. Urban cores and water have valid polygons but no profile data. Use `BGL 13.1` / `0.0` or `NRKART >= 100` to detect them.
10. `www.bgr.bund.de` product pages returned HTTP 400 to scripted requests (WAF), so we could not read them. GovData CKAN metadata and `download.bgr.de` worked.

## How to use this in our API

* **Routing.** If the point is in Niedersachsen, use LBEG BK50 (1:50k, state data). Otherwise, or if BK50 has no result, use BÜK200. Always also query SoilGrids for numeric properties with uncertainty.
* **BÜK200 lookup.**
  1. Run the layer-0 query to get the sheet, then the sheet-layer query to get `TKLE_NR`, `LEG_TEXT`, `Legende` and `BGL`.
  2. If there is a profile URL and the unit is not urban or water, fetch and parse FISBo once per `TKLE_NR` and cache it. The data is static, so cache it permanently.
  3. Return the legend text, the dominant soil type (highest `Flächenanteil`, optionally matched to the point's land use), and the horizon list with KA5 classes.
* **How the three sources fit together.**
  * **SoilGrids** (250 m, global, numeric with Q05/Q95 uncertainty) gives continuous estimates. It can be null at some points, including two of our test sites.
  * **BÜK200** gives authoritative German classification and parent material, plus representative horizon *classes*. It covers all of Germany but is coarse, and some fields are empty. It answered both SoilGrids-null sites.
  * **BK50** gives higher resolution and richer attributes, but only in Niedersachsen.
  * Show BÜK200 as the "soil type / parent material / typical profile" block and SoilGrids as the "numeric properties" block. Flag disagreements, e.g. BÜK200 says peat (h7) while SoilGrids SOC is low.
* **Attribution.** © BGR (Hannover) and the state geological surveys, BÜK200. Profile data is marked preliminary.
