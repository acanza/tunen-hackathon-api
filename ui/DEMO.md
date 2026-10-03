# 5-minute demo: Seggerde soil app

**One-line pitch:** public soil data for one real farm, made comparable across two state portals, with every number carrying
its source and its confidence. Where public data can't decide, the app says so and tells the farmer where to sample.

Run: `cd ui && npm run dev` (runs on the mock API; the map tiles still need internet). Open these once before you start, so tiles are cached:

- `/demo/before-after/FzvWonz6fmJVLZRzMyZX` (Bocksenden)
- `/field/pnZlGAIrQQMGSl0a3HbO/maps?p=bodenzahl&s=best` (Spraken)
- `/field/SEo2xyfcqiAjoec8ZXXa/maps?p=ph` and `/field/SEo2xyfcqiAjoec8ZXXa/sampling` (Mittelbreite)
- `/field/FzvWonz6fmJVLZRzMyZX/yield` (Bocksenden)
- `/field/MoYIfvnid4wXBDha0wJ3/sheet` (Heuweg)

## Script (≈ 45 s per step)

| # | Screen | Field | What to say |
|---|---|---|---|
| 1 | **Farm** (`/`), "Survey source" | – | 87 fields, 883 ha, **straddling a state border**: 43 in Lower Saxony, 44 in Saxony-Anhalt. Two survey portals and two data models on one farm. Lower Saxony publishes the soil score; Saxony-Anhalt only the soil class. That's the challenge's "different portal in every country" problem. Click **Soil texture**: the official class now covers the whole farm. |
| 2 | **Before / After**, step 1 | **Bocksenden** (west, 3.5 ha) | *Siloed sources.* The official survey covers only **55 %** of the field (score 39). Our model covers all of it, but at low confidence (likely 26–49). Switch to **Plant-available water**: SoilGrids says **~187 mm**, the soil-profile estimate **~83 mm**. Same field, different stories. |
| 3 | **Before / After**, step 2 | **Bocksenden** | *Confidence fusion.* One map: the official survey wins where it exists, the model fills the rest. **55 % official survey, 45 % our model**, score **38**, likely 30–46, medium confidence. The model-only part is grey-hatched. **"One map, and it tells you where it's sure."** |
| 4 | **Soil maps**, Soil quality score → Best, tick "Show source map" | **Spraken** (east, 38.8 ha) | Same fusion on the Saxony-Anhalt side: **73 % from the LAGB survey**, the rest model. Without the eastern data, our model said **~28**; with it, **~36**. Pulling the second portal changed the answer. |
| 5 | **Soil maps**, pH | **Mittelbreite** (east, 54 ha) | *Honesty.* The whole map is grey: pH likely **4.5–7.8**, which crosses the liming threshold of 5.5. "Public data can't decide liming here." → **Sampling plan** tab: 5 numbered GPS points where one lab result settles the decision for ~11 ha each. Download GPX. |
| 6 | **Yield pattern** | **Bocksenden** | A relative index from 8 years of satellite images (100 = this field's average), not tonnes. Type **7.5 t/ha**: expected yield per zone, and about **26 t** for the field. Tested on held-out seasons: **70 %** of the field lands on the correct side of its average. |
| 7 | **Spec sheet** → Farmer view, then Audit view | **Heuweg** (west, 1.5 ha) | Five plain sentences ("poor, typically sandy soil: score about 31 out of 100, official survey"; "we can't tell whether it needs lime"). Click a **[n]** marker: it jumps to the audit row with value, range, confidence drivers, method, source, licence and data date. **Every sentence traces to a number, every number to a source.** |

Spare fields: **Altenaer Weg** and **Cawi-Wiese** (west, mixed sources, like Bocksenden). Avoid tiny slivers (e.g. *Sandberg - 2*) unless asked about edge cases.

## Defending it: likely questions

**"Why is so much grey? Is the app broken?"**
No, that's the point. SoilGrids' 90 % range for pH spans 4.5–7.8, which includes both "needs lime" and "doesn't". Showing a
colour there would be false precision. We show the range and turn the uncertainty into an action: the sampling plan.

**"How do you know your numbers are right?"**
- Yield pattern: leave-one-season-out over 8 seasons and 616 field-seasons. **70 %** of the field lands on the correct side of its average, and the map beats a flat "all average" map in **72 %** of cases.
- Soil score model: **6.9 points** error against 38 official survey parcels (a farm average would give 10.0).
- SoilGrids texture matches the official class on only **24 %** of parcels. We measured that, and it's why the official class wins wherever it exists.

**"Where does the eastern soil score come from? Saxony-Anhalt doesn't publish it."**
Correct. LAGB publishes the class symbol (e.g. `lS4D`), not the score. We estimate it from western parcels with the same class and mark it
**medium** confidence, with that reason in the audit view. Loamy classes have no western match, so there the model fills in, visibly, on the source map.

**"Is this tonnes per hectare?"**
No. There's no harvest data, so we don't claim tonnes. The farmer supplies their usual yield and we supply the within-field pattern.

**"What about data licences?"**
SoilGrids is CC BY 4.0, Copernicus is open. The LBEG (Lower Saxony) and LAGB (Saxony-Anhalt) terms are **not yet verified**, and the audit view says so instead of hiding it.

**"Does it scale beyond this farm?"**
The pipeline is per-source and per-state: a new region means a new source adapter plus a priority in the "best" ranking. The UI only reads
`status`, `reason`, `confidence` and `source`, so new sources appear without UI changes.

## Where we deviate from the proposed datasets (`dataset.md`)

| Proposed source | What `dataset.md` suggested | What the app actually does | Why (say this if asked) |
|---|---|---|---|
| **ISRIC SoilGrids v2.0** | REST point queries; all properties incl. bulk density, CEC, coarse fragments | **WCS rasters** instead of REST. Uses clay/sand/silt, pH, SOC, and water content at 33/1500 kPa (for plant-available water). **Not shown:** bulk density, CEC, coarse fragments | REST is one point per call; the farm needs whole rasters (395 WCS requests in minutes). The unused properties feed no decision the app makes. Its uncertainty (5–95 %) is used, as proposed, for the confidence layer |
| **LBEG BK50** | Soil type, texture, plant-available water (nFKWe), yield capability, groundwater level | **Effectively not used.** Queried for coverage only; its plant-available water shows as "exists in the state map but isn't in our data yet" | The water attribute wasn't in what the NIBIS point query returned, and the server is rate-limited. Plant-available water comes from BÜK200 + profile lookup instead |
| **LBEG Bodenschätzung** | Headline soil score per parcel, 1:5k | Used as the headline score, but **only the parcels at one point per field**, so many western fields are "partial" | Same rate-limited server; the "best" map fills the rest from our model and shows where |
| **BGR BÜK200** | Fallback soil type outside Lower Saxony | **Bigger role:** basis of our plant-available-water estimate (soil-profile lookup per unit) and an input to the soil-score model, farm-wide | It was the only consistent soil-profile source on both sides of the border |
| **Open-Meteo (ERA5 + ICON)** | Time dimension: soil moisture/temperature, forecast | Daily ERA5 2019–2026 used **inside the yield model** (spring water balance, dry-year scenarios). **No soil-moisture time series or forecast in the app** | All 87 fields sit in 4 weather cells (~9 km), too coarse to show per field. Time is reflected through 8 seasons of satellite history instead |
| **Copernicus DEM GLO-30** | Elevation, slope, aspect | Slope, wetness index, relative elevation used as **model inputs**; **no terrain map in the app** | The farm is flat; terrain matters as a predictor, not as a map for the farmer |
| **Extras** (SWI, SMAP, LGLN DGM1, GÜK200, BOSIS M-V, EMIT) | Stretch goals | **None used** | Time went into confidence and cross-state fusion |

**Added, not in `dataset.md`:**
- **Sentinel-2 L2A NDVI 2019–2026** (Element84 Earth Search, no account). This is the backbone of the yield pattern. Soil maps can't show variation inside a field: 44 of 87 fields are smaller than one SoilGrids pixel.
- **LAGB Saxony-Anhalt soil data** (open WFS). `dataset.md` said "stay anchored on Niedersachsen", but this farm is ~70 % in Saxony-Anhalt. A second state was unavoidable here, and it doubles as our extendability proof (the role `dataset.md` gave to M-V's BOSIS).

**One-liner for judges:** "We used the proposed core sources where they work at field scale, replaced point APIs with rasters, and added
satellite history and a second state portal, because this real farm crosses a state border and is smaller than the global soil map's pixels."

## Don't overclaim

- **Sampling plan, management signals, crop suitability and the "where sources disagree" step are previews on mock data** (they carry a badge). Say "this is the next data step", not "this is computed".
- The eastern soil score is an estimate from the class, not an official number.
- The yield index comes from satellite crop growth (NDVI), not from harvests.
