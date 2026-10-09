# LBEG NIBIS soil WMS: BK50 + Bodenschätzung, EDA

Source: LBEG (Landesamt für Bergbau, Energie und Geologie, Niedersachsen), NIBIS map server.
Data pulled on 2026-10-03 for the 10 shared test sites.

**Short version:** PkgId=24 has both the BK50 soil map and the Bodenschätzung layers. It is a WMS
with no WFS, but `GetFeatureInfo` with `INFO_FORMAT=application/geo+json` returns clean JSON (attributes plus the
full polygon). A request takes about 0.33 s. You need one request per layer. The data covers Niedersachsen only; a point in Hamburg comes back
as an empty `FeatureCollection`.

## Files

| Path | What |
|---|---|
| `fetch.py` | Reproducible fetch + flatten (`uv run fetch.py [--legends] [--flatten]`) |
| `raw/<site>__<lon>_<lat>__<layer>.geojson` | Untouched GetFeatureInfo bodies (10 sites × 24 layers = 240 files) |
| `raw/<site>__<lon>_<lat>__{L816,L849}.txt` | The same queries as `text/plain`, for humans |
| `raw/_manifest.json` | Per request: final URL, HTTP latency, attempts, total time, feature count, error |
| `raw/legends/*.png` | `GetLegendGraphic` images (source for the class tables below) |
| `nibis_points_long.csv` | Long format: `site, lon, lat, source_layer, layer_title, feature_idx, attribute, value, unit_if_known`. Meta rows: `_feature_count` per request, `_contains_point` per feature, `_error` on failure |

Note: `raw/` is 7.7 MB because the landscape layers (L29, L58, L848, L487) return huge region polygons. Do not request
those from an API hot path, or remove the geometry.

## Endpoints

| Endpoint | Content |
|---|---|
| `https://nibis.lbeg.de/net3/public/ogc.ashx?PkgId=24` | "Bodenkarten WMS – Dienst LBEG": BK50 and its evaluations, Bodenschätzung (BS5), BÜK500, protected soils, etc. 166 queryable layers. **This is the right package.** |
| `https://nibis.lbeg.de/net3/public/ogc.ashx?NodeId=989` | BK50 map only (same `L816`) |
| `https://nibis.lbeg.de/net3/public/ogc.ashx?NodeId=2201` | `L1790` "GLÖZ 5 Tongehalte (25 %)": clay > 25 % flag, **only for erosion-prone (KWasser1/2) field blocks**. Empty at all 10 test sites |

GetCapabilities: `…ogc.ashx?PkgId=24&Service=WMS&Request=GetCapabilities` (WMS 1.3.0, about 1 MB XML, MaxWidth/MaxHeight 1800).

## Working request recipe

```
GET https://nibis.lbeg.de/net3/public/ogc.ashx?PkgId=24
  &SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo
  &LAYERS=L816&QUERY_LAYERS=L816&STYLES=
  &CRS=EPSG:25832
  &BBOX=x-5,y-5,x+5,y+5          # 10 m box centred on the point (x,y in EPSG:25832, easting/northing)
  &WIDTH=101&HEIGHT=101&I=50&J=50   # odd size -> pixel (50,50) is exactly the centre
  &INFO_FORMAT=application/geo%2Bjson   # '+' MUST be URL-encoded
  &FEATURE_COUNT=10
```

A real URL (Hildesheimer Börde):
`https://nibis.lbeg.de/net3/public/ogc.ashx?PkgId=24&SERVICE=WMS&VERSION=1.3.0&REQUEST=GetFeatureInfo&LAYERS=L816&QUERY_LAYERS=L816&STYLES=&CRS=EPSG%3A25832&BBOX=564892.09%2C5785927.95%2C564902.09%2C5785937.95&WIDTH=101&HEIGHT=101&I=50&J=50&INFO_FORMAT=application%2Fgeo%2Bjson&FEATURE_COUNT=10`

- **Coordinate systems:** CRS:84, EPSG:4326, 4258, 3857, 25832, 25833, 4647, 31466–31469, 3038–3047, 5649/5650 and 32631–32633 are advertised.
  EPSG:25832 avoids the WMS 1.3.0 lat/lon axis swap of EPSG:4326. `CRS=CRS:84` with a lon/lat BBOX also worked in a test.
- **INFO_FORMAT:** `text/html`, `text/plain`, `text/html;fragment`, `text/html;cardo`, `application/geo+json`,
  `application/geojson`. All give the same attributes. Use GeoJSON.
- **Response:** a `FeatureCollection`. Each feature has `properties` (German attribute names) and a `geometry`, which is
  the full map polygon in **EPSG:4647** (UTM32 with a `32` prefix on the easting, e.g. `32564760.93`),
  whatever CRS you asked for. A point with no data returns HTTP 200 with `"features":[]`. In `text/plain` that is
  `- Keine Treffer für diese Ebene -`.
- **Several layers in one request** (`QUERY_LAYERS=L816,L849,...`) works, but the features carry **no layer
  ID**, and only `FL_NR` hints at the source. Make one request per layer.
- **Scale hints** (`MaxScaleDenominator` 167 410 for BK50 layers) are ignored by GetFeatureInfo. Querying at about 1:350 works.

## Relevant layers (PkgId=24)

| Layer | Title | Attributes returned |
|---|---|---|
| **L816** | BK50 – Karte | `FL_NR, NRKART, PRONUM, BOTYP, BOTYP_KLARTEXT, PSONST, MHGW, MNGW, NUTZUNG, GEOTYP` |
| **L849** | BS5 – Bodenzahl der Bodenschätzung | `KLASSENZEICHEN, KLASSENZEICHEN_KLARTEXT, KLASSENZEICHEN_SEP, BODENZ, ACKERZ, AREA, TK25, UP_DATE, …` |
| **L837** | BK50 – Ertragsfähigkeit | `BFR` |
| **L838** | BK50 – Grundwasserstufe | `GWS` |
| **L839** | BK50 – Nutzbare Feldkapazität des eff. Wurzelraumes | `NFKWE, NFKWE_STUFE` |
| **L821** | BK50 – Pflanzenverfügbares Bodenwasser (1991–2020) | `WPFL, WPFLKLASSE, WPFLKLASSE_TEXT` |
| **L823** | BK50 – Effektive Durchwurzelungstiefe | `WE, WEKLASSE, WEKLASSE_TEXT` |
| L820 | Standortabh. Verdichtungsempfindlichkeit | `VDST, VDST_TEXT` |
| L822 | Gefährdung der Bodenfunktionen durch Verdichtung | `VDBF` (text) |
| L842 | Sickerwasserrate (1991–2020) | `SWRKLASSE` |
| L843 | Austauschhäufigkeit des Bodenwassers | `AHKLASSE` |
| L841 | Bindungsstärke Oberboden für Cadmium | `FSMO_CD` |
| L1439 / L1440 | Bodenkundl. Feuchtestufe Frühjahr/Sommer | `BKF, BKF_FJZ_1991_2020, BKF_SZ_1991_2020, EIGNUNG` |
| L845 / L846 | Kohlenstoffreiche Böden (BHK50) | `KATEGORIE, BODEN` / `+ TORFMAECHTIGKEIT, BODENTYP, NUTZUNG` |
| L476 | Sulfatsaure Böden 0–2 m | `SSB_KLASSE, INHALT, KURZTEXT, MASSNAHME` |
| L829 / L828 | Schutzwürdige Böden (Fruchtbarkeit / bes. Standorteigenschaften) | `KLASSE, KATEGORIE, TYP` |
| L848 / L29 / L58 | Bodenregion / Bodengroßlandschaft / Bodenlandschaft | `BR_NAME, BGL_NAME, BL_NAME` |
| L487 | BÜK500 | `KLARTEXT` (free-text soil association) |
| L1422–L1436, L1711–L1717 | Climate-scenario evaluations (RCP2.6/8.5) | `MBM/AKWH/AH/AES, MIN, MAX` |
| L2081–L2200 "Methode BK50…" | **Not data.** They only return `{id, objectid, up_date}` (method-documentation polygons) | |

**Missing from the WMS: texture and clay %.** BK50 per-horizon data (`BK_HORIZONT`: `HNBOD` texture, `OTIEF/UTIEF`, etc.,
linked by `PRONUM`) exists in the BK50 product (GeoBerichte 40, ch. 4) but is not served through the WMS. The only
texture signals you can query are:
1. the **Bodenart** in the Bodenschätzung `KLASSENZEICHEN` (only on surveyed farmland),
2. `GEOTYP` (geological profile type) and the soil type in `BOTYP`,
3. the L1790 clay > 25 % flag (only on erosion-prone fields).

## Attributes, translations, units and codes

### L816 BK50 – Karte
| Attribute | English | Notes |
|---|---|---|
| `FL_NR` | polygon id | Shared by all BK50 evaluation layers, so you can join on it |
| `NRKART` | mapping unit no. | Prefix = land-use variant: 1xx xxx arable, 2xx xxx grassland, 3xx xxx deciduous forest, 4xx xxx coniferous forest, ≥500 000 other use. **Negative = not soil:** −1 water, −3 made ground (Auftrag), −4 excavated (Abtrag), −6 outside Niedersachsen, −8 Wurten (dwelling mounds) |
| `PRONUM` | profile no. | Key to the horizon table (not served) |
| `BOTYP` / `BOTYP_KLARTEXT` | soil type (KA5 code / German name) | e.g. `T-L3` = Mittlere Tschernosem-Parabraunerde (chernozemic Luvisol), `HHv5` = very deep earthified raised bog |
| `NUTZUNG` | land use | `A` arable, `G` grassland, `FL` deciduous forest, `FN` coniferous forest, `N` other |
| `MHGW` / `MNGW` | mean high / low groundwater level | **dm below surface**. Null where there is no groundwater influence |
| `PSONST` | remarks | e.g. "MHGW wurde abgesenkt" (groundwater lowered by drainage), "Auftragsfläche" |
| `GEOTYP` | geological profile type | e.g. `Lol=Lg_f(qM)` loess loam over …, `Miwa` marine tidal-flat deposits |

### L849 Bodenschätzung (official German soil valuation, 1934 onwards; farmland only)
| Attribute | English | Notes |
|---|---|---|
| `BODENZ` | Bodenzahl (soil score) | 7–100. For grassland it is the **Grünlandgrundzahl** |
| `ACKERZ` | Ackerzahl (arable score) | BODENZ ± adjustments for climate, slope, etc. For grassland it is the Grünlandzahl. Higher = more productive. National mean is about 45 |
| `KLASSENZEICHEN` | class symbol | **Arable:** `<Bodenart><Zustandsstufe 1–7><Entstehung>`, e.g. `L2Lo` = Lehm, condition 2, loess. **Grassland:** Roman numeral condition (I–III), e.g. `LI-`, `MoII-` |
| `KLASSENZEICHEN_SEP` | the same, `;`-separated | Easiest to parse: `[Bodenart, Zustand, Entstehung]` |
| `KLASSENZEICHEN_KLARTEXT` | plain German | e.g. "lehmiger Sand/hohe Leistungsfähigkeit/Lössböden" |

Bodenart codes run sand to clay: `S` Sand, `Sl` anlehmiger Sand, `lS` lehmiger Sand, `SL` stark lehmiger Sand, `sL` sandiger
Lehm, `L` Lehm, `LT` schwerer Lehm, `T` Ton, `Mo` Moor (peat). Entstehung: `D` Diluvium, `Lo`/`Lö` Löss,
`Al` Alluvium, `V` Verwitterung, `Vg` stony weathering.
Zustandsstufe: 1 is the best developed, 7 the poorest.

### BK50 evaluation layers (classes taken from `raw/legends/*.png`)
| Attribute | English | Unit / classes |
|---|---|---|
| `NFKWE` (L839) | available water capacity of the effective root zone (nFKWe) | **mm**. `NFKWE_STUFE`: 1 ≤50 very low · 2 >50–90 low · 3 >90–140 medium · 4 >140–200 high · 5 >200 very high |
| `WPFL` (L821) | plant-available soil water, 1991–2020 climate | **mm**. nFKWe **plus capillary rise from groundwater**, so it is higher than NFKWE on groundwater sites (Emsland 193 → 287). `WPFLKLASSE`: 1 <50 · 2 50–100 · 3 100–150 · 4 150–200 · 5 200–250 · 6 250–300 · 7 ≥300 mm, with text in `WPFLKLASSE_TEXT` |
| `WE` (L823) | effective rooting depth | **cm** (110 → class "sehr hoch" ≥11 dm). `WEKLASSE`: 1 <3 dm · 2 3–5 · 3 5–7 · 4 7–9 · 5 9–11 · 6 ≥11 dm |
| `BFR` (L837) | Ertragsfähigkeit (natural yield potential / soil fertility) | 1 äußerst gering … 4 mittel … 7 äußerst hoch (7-step ordinal scale) |
| `GWS` (L838) | Grundwasserstufe (groundwater level class) | GWS1 very shallow (MHGW above surface, MNGW ≤4 dm) · GWS2 shallow (MNGW 4–8) · GWS3 medium (MNGW 8–13) · GWS4 deep (MNGW 13–16) · GWS5 very deep (MNGW 16–20) · GWS6 extremely deep (>20) · GWS7 no groundwater influence (MHGW >20 dm) |
| `VDST` (L820) | compaction sensitivity | text in `VDST_TEXT` (keine … äußerst hoch) |
| `SWRKLASSE` (L842) | percolation-water rate class | Legend: ≤0, >0–50, >50–100 … >600 mm/a in 50 mm steps. **Assumed** class 1 = ≤0, so class *k* ≈ (k−2)·50 to (k−1)·50 mm/a. Not verified |
| `BKF` (L1439/40) | soil moisture level | KA5 Feuchtestufe 0 dürr … 11 open water |

## Latency and reliability (240 GeoJSON requests, sequential, 0.4 s sleep)
- HTTP latency: **median 0.33 s, p90 0.46 s, max 0.76 s**.
- **About 2.5 % of requests (6/240) hung** with no response. Each succeeded on the first retry. With a 10 s timeout
  those calls took about 12.5 s in total. In a first run with a 60 s timeout, the stalls were much longer. **Use a short
  timeout (3–5 s) and retry.**
- No HTTP errors and no rate limiting seen. Responses are anonymous. The server injects a
  `cardo3SessionGuid` into the capabilities URLs; ignore it.

## Per-site results

Values from the polygon that contains the point (`_contains_point = True`). The "SoilGrids" column is from `../soilgrids_eda`.

| Site | BK50 soil type (`BOTYP`) | Use | Bodenschätzung KZ | Boden-/Ackerzahl | nFKWe mm (Stufe) | WPFL mm | We cm | BFR | GWS | MHGW/MNGW dm | SoilGrids |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Hildesheimer Börde 9.95,52.22 | T-L3 Tschernosem-Parabraunerde | A | `lS3Lo` | 71 / 74 | 228 (5) | 228 | 110 | 7 | 7 | – | data |
| Hildesheim edge 9.95,52.12 | S-L3 Pseudogley-Parabraunerde | A | – (no BS polygon) | – | 225 (5) | 225 | 110 | 7 | 7 | – | **null** |
| Lüneburger Heide 10.05,53.05 | B-P2 Braunerde-Podsol | FN | – (forest) | – | 126 (3) | 126.9 | 120 | 3 | 7 | – | data |
| Emsland 7.35,52.75 | G-P3 Gley-Podsol | FN | – (forest) | – | 193 (4) | 287.3 | 120 | 4 | 5 | 7 / 17 | data |
| Wesermarsch 8.40,53.35 | MC4 Tiefe Kalkmarsch | G | `LI-` (grassland) | 84 / 84 | 139 (3) | 247.4 | 70 | 5 | 3 | 3 / 8 | data |
| Teufelsmoor 8.90,53.25 | HHv5 Sehr tiefes Erdhochmoor (peat 160 cm per L846) | G | `MoII-` (grassland) | 37 / 37 | 225 (5) | 259.5 | 40 | 1 | 3 | 4 / 9 | data (shows 36 % clay, which is wrong) |
| Solling 9.55,51.75 | pB3 podsolierte Braunerde | FN | – (forest) | – | 129 (3) | 129.3 | 105 | 3 | 7 | – | data |
| Hannover centre 9.73,52.37 | **NRKART −3 Auftragsfläche** (made ground) | – | – | – | null | no feature | null | null | null | – | **null** |
| Farmland 10.10,52.18 | S-T3 Pseudogley-Tschernosem | A | `L2Lo` | 90 / 94 | 228 (5) | 228 | 110 | 7 | 7 | – | **null** |
| Hamburg 9.95,53.55 | **no features in any layer** | | | | | | | | | | null |

Other findings: Wesermarsch is flagged as sulfate-acid-soil class `GR_2C` (L476). Teufelsmoor is in the carbon-rich soils
layers (L845/L846 "Hochmoor"). Börde and the farmland site are "Böden mit hoher natürlicher Bodenfruchtbarkeit" (L829, BFR 7).

## Coverage behaviour
- **Outside Niedersachsen (Hamburg):** every layer returns HTTP 200 with an empty `features` array. You do not get the
  `NRKART=-6` code. Treat empty as "no coverage" and fall back to another source (e.g. BÜK200).
  Bremen was not tested; the GLÖZ layer says it covers Bremen, but BK50 is Niedersachsen-only.
- **Urban areas (Hannover):** BK50 has full coverage, but the polygon is `NRKART=-3` / `PSONST="Auftragsfläche"`
  (made ground) and all derived values are null. L821/L842/L843/L1439/L1440 return no feature at all. The Bodenschätzung is empty.
  For a coarse hint, BÜK500 (L487) still gives a natural-soil association (here: floodplain Gley-Auenböden).
- **Bodenschätzung covers agricultural land only.** Forests (Heide, Emsland, Solling) and settlements are empty. Some
  arable BK50 polygons also have no BS polygon at the point (Hildesheim edge).
- **BK50 fills gaps that SoilGrids leaves:** all 3 SoilGrids-null sites inside Niedersachsen have full BK50 data
  (Hildesheim edge, farmland 10.10/52.18), or at least an explicit made-ground flag (Hannover).

## Gotchas
1. **Use a small BBOX.** The hit tolerance is a few *pixels*. With a 100 m / 101 px box, neighbouring polygons
   about 1.5 m away were also returned, and **the first feature was not always the one containing the point**
   (Wesermarsch returned MN4 first, but the point is in MC4). A 10 m box gives about 0.1 m pixels and returns exactly one
   polygon. As a safeguard, `fetch.py` also tests point-in-polygon (`_contains_point`).
2. URL-encode `+` in `application/geo+json`. A raw `+` becomes a space, and the server answers with an XML
   `ServiceException` ("Der Wert 'application/geo json' … ist nicht zulässig").
3. Multi-layer requests lose the layer identity. Query one layer per request.
4. The returned geometry is always EPSG:4647 with the zone prefix. Subtract 32 000 000 from x to get EPSG:25832.
5. `null` vs missing: on made ground some layers return a feature with all-null attributes and others return none.
6. Units are not in the response. `WE` is in cm but the legend uses dm, `MHGW/MNGW` are in dm, and `NFKWE/WPFL` are in mm.
7. `BODENZ/ACKERZ` mean different things on grassland. Check whether the `KLASSENZEICHEN` uses a Roman numeral.
8. The "Methode BK50…" layers look like attribute layers but contain no data.
9. The landscape layers (L29/L58/L848/L487) return very large polygons (up to 850 KB per response).

## How to use this in our API
- **Call pattern:** for a lon/lat inside Niedersachsen, transform to EPSG:25832 and send in parallel (or a small
  bounded pool): L816, L849, L839, L821, L823, L837, L838 (+ optionally L820, L846, L476). Join on `FL_NR`, drop the geometry, and
  cache by `FL_NR` / BS polygon id. Budget about 0.35 s per call, with a 3–5 s timeout and 1 retry.
- **What to expose:** soil type (BOTYP + Klartext), land-use variant, Bodenzahl/Ackerzahl + Klassenzeichen
  (parsed into Bodenart / Zustand / Entstehung), nFKWe mm + class, WPFL mm, rooting depth, groundwater class and MHGW/MNGW,
  yield potential (BFR), peat thickness and flags (sulfate-acid, carbon-rich, protected soil).
- **Compared with ISRIC SoilGrids (250 m, global, continuous properties by depth, with Q0.05–Q0.95 uncertainty):**
  - **Available water: use BK50 as the override** in Niedersachsen. `NFKWE` is a mapped value (polygons at 1:50 000)
    in mm over the actual effective root zone, and the derived classes follow the German KA5 method. SoilGrids' `wv0033 − wv1500` is a
    model estimate per depth layer with wide intervals. Convert SoilGrids to mm over the BK50 rooting depth (`WE`) to compare.
  - **Soil type, peat and groundwater: use BK50.** SoilGrids misreads peat as mineral clay (Teufelsmoor 36 % clay),
    and it has no groundwater information.
  - **Clay % / texture: BK50 via WMS cannot replace SoilGrids numerically.** There is no clay % field. Use it as a
    *categorical check or override*: map the Bodenschätzung Bodenart (S…T, Mo) or the BK50 soil type to texture
    classes, and constrain or flag the SoilGrids clay median (e.g. KZ `L`/`LT`/`T` → clay should be ≥ about 17–25 %;
    `S`/`Sl` → low clay; `Mo` → organic, ignore the mineral clay). Real per-horizon clay needs the BK50 horizon table, which is not
    in the WMS (a data request to LBEG is needed).
  - **SoilGrids nulls:** BK50 gives data at the SoilGrids-null farmland points, and an explicit "made ground" code in the city.
  - Keep SoilGrids for pH, SOC, bulk density, CEC, continuous depth profiles, uncertainty, and anything outside Niedersachsen.
- **Attribution / licence:** cite "© LBEG, NIBIS® Kartenserver". Check the LBEG terms of use for API redistribution.
  The GLÖZ-5 dataset metadata states CC BY 4.0; the BK50 terms were not checked.

## Sources
- GetCapabilities: https://nibis.lbeg.de/net3/public/ogc.ashx?PkgId=24&Service=WMS&Request=GetCapabilities
- BK50 Erläuterungen, GeoBerichte 40 (NRKART ranges, field definitions, Feuchtestufe table): https://nibis.lbeg.de/DOI/dateien/GB_40_Text_13_web_neu.pdf
- Layer pages: https://nibis.lbeg.de/net3/public/ikxcms/default.aspx?pgid=1017 (Ertragsfähigkeit), …pgid=1018 (Grundwasserstufe)
- GLÖZ 5 clay metadata: https://nibis.lbeg.de/geonetwork/srv/api/records/c2d52d14-4130-49b0-bd48-6a5e572daea3
- Class tables: `raw/legends/*.png` (GetLegendGraphic)
- Bodenschätzung code meanings (Bodenart, Zustandsstufe, Entstehungsart) come from the standard
  Acker-/Grünlandschätzungsrahmen and were not re-verified against an LBEG document.
