# Tunen Hackathon 10/26 \- Soil aggregation API

Author: [Alexandre Shinebourne](mailto:alex@tunen.ai) Date: 3 Oct 2026

Hey there\! Thanks for joining us for the **Tunen Soil Aggregation API hackathon**. We’re looking forward to a day of collaborating, problem solving, playing with data and can’t wait to see what you come up with\!

## Background

### What we do at Tunen

Our main focus is reducing the friction of data entry/collection in agriculture. Modern arable farms produce huge amounts of complex data (GPS traces, field records, application maps, machine service invoices, equipment telemetry etc.). Farmers do not have the resources to manage these datasets themselves. However, a unified field state can provide huge benefits to many industry stakeholders; farmers but also food manufacturers, agronomists, scientists and equipment manufacturers.

Achieving a unified field state is not a trivial task \- the data is complex, manual data entry is time consuming and error prone, datasets are siloed in separate systems or even mediums (paper, email, API, app, PDFs etc.). At Tunen we solve these problems with solutions that combine increased automation in the data entry and collection process as well as close collaboration with the farmer.

### Why soil matters in agriculture

For those that enjoy a bit of historical context. In the late 40s, we saw the beginning of the Green revolution. This transformation in agriculture had huge impacts on global development, reducing the agricultural workforce, changing the fabric of society and allowing for significant population and economic growth. The revolution was achieved through the explosion of heavy machinery, synthetic chemical pesticides, artificial fertilisers and high-yielding crop varieties.

While there are yield gains to be had from blanket/uniform applications of fertiliser products, these products are expensive (sensitive to geopolitical factors like oil costs) and overapplication wasteful. Modern farms can optimise their costs while still retaining the yield advantages offered by artificial fertiliser application by better understanding their soil. By mapping out the soil, farms can create tailored application plans and even sub-field level application maps. This form of agriculture is known as precision agriculture and is achieved through a combination of soil mapping data science and sophisticated machinery that use the soil maps to vary the application rate in realtime.

So what should you be looking for? A handful of parameters that you can gather remotely do most of the work. Farmers do on-farm probing for nutrients, but this data is not publicly available. Texture — the mix of sand, silt and clay — drives nearly everything else: sandy soils drain fast and dry out, clay holds water but compacts easily. pH decides whether the nutrients present are actually available to the plant. Organic carbon is the engine room, feeding soil life and holding moisture. Plant-available water (nFK) tells you how much of that stored water a crop can genuinely drink. And Germany's Bodenzahl squeezes all of it into a single 0–100 score. Find these, and you've got a farm's fingerprint 

All that to say that soil data is extremely useful \- having a coarse overview is better than nothing but having highly granular data can be utilised to guide farm management practices. Bringing us nicely to today’s hackathon 🙂

### Tips

We encourage you to explore and be as ambitious as you can. However, we recommend that you keep the following in mind:

* What’s most important is you finish the day with something to show for  
* Don’t underestimate the time it takes to prepare a decent demo/present your work (All is won or lost in the presentation)  
* Be ambitious \- try get something working quickly and then experiment with how far you can push it  
* You’re likely to come up with something way more impressive if you embrace AI to support the development process  
* Use whatever will get you ‘hacking’ faster \- I recommend Python \+ a web framework that can make powerful visualisation like React

## The problem spec: Soil data aggregation API

There are several sources of soil data in Germany, all with different resolutions, strengths and weaknesses. Today you will build a backend service that unifies these sources behind a single API, and a UI that consumes that API to display soil data on farm fields.

The core of the challenge is the aggregation service. The UI is how you prove it works. Your UI should talk only to your own API, not to the third-party sources directly. Fetching, harmonising and serving the data is the backend's job.

Focus on the five parameters from the background section, for topsoil (0–30 cm):

| Parameter | Why it matters | Starting sources |
| :---- | :---- | :---- |
| Texture (clay / sand / silt) | Drives drainage, workability and compaction risk | SoilGrids (numeric %), LBEG BK50 (Bodenart class), Bodenschätzung (Klassenzeichen) |
| pH | Controls nutrient availability | SoilGrids, OpenLandMap (Earth Engine) |
| Organic carbon | Soil life and water retention | SoilGrids, OpenLandMap (Earth Engine) |
| Plant-available water (nFK) | How much stored water the crop can actually use | LBEG BK50 (nFKWe), SoilGrids (derived from water content at 33 and 1500 kPa) |
| Bodenzahl | The 0–100 score German farmers and agronomists recognise | LBEG Bodenschätzung (BK50 Ertragsfähigkeit as a related proxy) |

These are starting points, not an exhaustive list. Note that several German sources are categorical (texture classes, soil types) rather than numeric. Converting them into comparable values is part of the challenge, and one of the more interesting parts.

### Part 1: The aggregation API

The API should take a list of GeoJSON polygons (representing a farm's fields) and return a set of raster layers for each field: one per soil parameter per data source. As the data is spatial, you'll return images rather than single values. If a source is low resolution, its image will be uniform across the field. If it has sub-field granularity, you'll see variation across the image.

For each layer, return a rendered PNG with its bounds, so the UI can drop it straight onto a map as an image overlay. Also return the underlying values (a GeoTIFF, or a JSON grid plus summary stats), so the UI can show real numbers on hover, draw accurate legends and compare sources.

Here's a suggested request and response shape. You're free to deviate if you can justify it, since good API design is part of what we're judging.

POST /soil/layers

* "fields": { "type": "FeatureCollection", "features": \[ ... \] },  
* "parameters": \["texture", "ph", "soc", "nfk", "bodenzahl"\],  
* "sources": \["soilgrids", "lbeg\_bk50", "lbeg\_bodenschaetzung", "derived"\],

| {  "fields": \[{    "field\_id": "f1",    "bounds": \[\[52.31, 9.71\], \[52.32, 9.73\]\],    "layers": \[{      "parameter": "clay",      "source": "soilgrids",      "unit": "%",      "png\_url": "/rasters/f1/clay/soilgrids.png",      "geotiff\_url": "/rasters/f1/clay/soilgrids.tif",      "stats": { "min": 18.2, "mean": 21.5, "max": 24.0 },      "colormap": { "min": 0, "max": 60, "name": "viridis" }    }\]  }\]} |
| :---- |

**Derived values.** In addition to a response per data source, provide your own derived layers that consider all available sources for a parameter. A trivial starting point is a mean or weighted average. The spread between sources is just as interesting: it highlights where the data is most and least certain. SoilGrids' built-in 5th–95th percentile range makes a good baseline for this. Treating "derived" as just another source in your API keeps the design clean.

**Extendability and freshness.** Think about how easy it would be to add a new data source tomorrow. Ideally it's one new adapter, not changed throughout the codebase. Your service should also be able to pull fresh data from the sources programmatically, via a refresh endpoint, button or CLI command.

### Scope: what "done" looks like

There's more here than most teams will finish in a day, so prioritise:

- **Must have:** An API that accepts GeoJSON fields and returns per-source layers for the five required parameters, from at least SoilGrids plus one LBEG source. A map UI that displays the fields and toggles between parameters and sources.  
- **Should have:** Derived mean and spread layers, an uncertainty heatmap, and a refresh mechanism.  
- **Stretch:** Overlaying soil data with geology (BGR GÜK200 rock types) or terrain (slope and altitude from Copernicus DEM) to visualise relationships between physical properties.

### Judging criteria

You will be able to demonstrate your work to us in your final presentation. The Tunen specific track metrics/judging angles are highlighted bellow:

* Data sources  
  * Extendability to different data sources  
  * Ability to pull fresh data from the data sources programmatically (refresh button, refresh CLI command)  
  * Well informed data modeling from an agriculture perspective  
* The API  
  * Is the API well defined \- what do the request and response models look like  
  * Interesting derived values (mean avg across different data sources, variance etc.)  
* Visualisation and UI  
  * Several different interesting visualisations focusing on the most interesting parameters to display from an agricultural perspective  
  * \[Bonus points\] Bringing in other complementary datasets and visualising patterns with the soil data  
  * Cool factor  
* Presentation/live demo  
  * Did it work?  
  * How effectively did you communicate your work with the rest of the room?

## Getting started

We have provided you with some sample GeoJSON fields from Julius’ brother’s farm: [LuF-Seggerde-Dev-fields.geojson](https://drive.google.com/file/d/1l4JQ-CnG9hiFf2h5gWCfETdm566dinkt/view?usp=sharing). You can use these or a sub-set of these for making requests to your soil aggregation API.

Below are the two tables, focused on soil (plus the terrain/moisture layers for derived data). I've verified the main endpoints are live; everything in *Start here* needs no account and returns a value for a single coordinate with one or two HTTP calls. We want you to use free and open datasets \- but don’t restrict yourself to just what is listed here.

API liveness and payload check available here 

- Fetching soil for a (lat, long) point [soil\_api\_check.ipynb](https://colab.research.google.com/drive/1OnGrppAKHW1ljtAl9XtI5NbhT51SJcUQ?usp=sharing)  
- Fetching soil over an area (raster) [soil\_raster\_map.ipynb](https://colab.research.google.com/drive/1e8TY-z3_F5qiZQ97iP1PtbPLbwXdKJLW?usp=sharing)

**Start here — core datasets**

| Source | What it gives you | Coverage / resolution | Access | Gotchas |
| :---- | :---- | :---- | :---- | :---- |
| **ISRIC SoilGrids v2.0** | Clay, sand, silt, pH, SOC, bulk density, CEC, coarse fragments, water content at 10/33/1500 kPa — at 6 standard depths, with mean \+ 5th/50th/95th percentiles | Global, 250 m | REST: `https://rest.isric.org/soilgrids/v2.0/properties/query?lon=&lat=&property=clay&depth=0-5cm&value=mean` — JSON back, no key | Values are in "mapped" units (e.g. clay in g/kg, pH ×10) — divide before displaying. Built-in uncertainty makes this the natural baseline for your variance/confidence layer |
| **LBEG BK50 – Bodenkarte 1:50.000 (NIBIS)** | Soil type, texture, nFKWe (plant-available water), Ertragsfähigkeit (yield capability), Grundwasserstufe | Niedersachsen, 1:50k | WMS GetCapabilities: `https://nibis.lbeg.de/net3/public/ogc.ashx?PkgId=24&Service=WMS&Request=GetCapabilities` — use `GetFeatureInfo` for point queries | WMS only (no WFS), so point queries go via GetFeatureInfo; German attribute names; check supported CRS in capabilities (EPSG:25832 is safest). Best-resolution *German* soil data you'll get for free — the source that makes the aggregation interesting |
| **LBEG – Bodenschätzung (Bodenzahl / Ackerzahl, Klassenzeichen)** | Official soil productivity score (0–100) and texture/origin class per parcel | Niedersachsen, 1:5k | Same NIBIS WMS package (PkgId=24), separate layers | Bodenzahl is *the* number German farmers and agronomists recognise — a great "headline" parameter for the UI |
| **BGR BÜK200** | Federal soil overview map: legend unit, dominant soil type, parent material | All of Germany, 1:200k | ArcGIS REST MapServer: `https://services.bgr.de/arcgis/rest/services/boden/buek200/MapServer` — supports JSON/GeoJSON `query` with a point geometry | Coarse, but it's the only free source with consistent *nationwide* soil-type coverage — use it as the fallback when a coordinate falls outside Niedersachsen |
| **Open-Meteo (ERA5-Land archive \+ DWD ICON)** | Soil moisture and soil temperature at 4 depth bands, precipitation, ET₀ — historical and forecast | Global / Europe, \~9 km (ICON \~2 km) | REST, no key: `https://archive-api.open-meteo.com/v1/archive?latitude=&longitude=&hourly=soil_moisture_0_to_7cm,...` | The easiest way to add a *time* dimension to the soil profile (answers the "how does soil change dynamically" consideration) |
| **Copernicus DEM GLO-30** | Elevation → slope, aspect | Global, 30 m | AWS Earth Search STAC (`https://earth-search.aws.element84.com/v1`, collection `cop-dem-glo-30`) — public COGs, read with `rasterio` | Needs `rasterio`/`rioxarray`; read a small window around the point rather than the whole tile |

**Stretch — if the core is working by early afternoon**

| Source | What it gives you | Coverage / resolution | Access | Gotchas |
| :---- | :---- | :---- | :---- | :---- |
| **Copernicus Land – Soil Water Index (SWI)** | Root-zone soil moisture index, daily | Europe, 1 km | Via Copernicus Data Space Ecosystem (OData API / S3) | Needs a **free CDSE account** — register before the day. Daily files are large; grab a small time window |
| **NASA SMAP L4** | Root-zone soil moisture, 3-hourly | Global, 9 km | NASA Earthdata (AppEEARS point sampler or GIBS tiles) | Needs a **free Earthdata login**. Coarse — most useful as a sanity check on the Open-Meteo numbers |
| **LGLN DGM1** | 1 m terrain → field-scale slope, wetness index | Niedersachsen, 1 m | WMS/WCS via LGLN open geodata (Datenlizenz Deutschland) | Much heavier than GLO-30; only worth it if a team wants sub-field slope/erosion or wetness visualisations |
| **BGR GÜK200 (geology)** | Parent rock / geological unit | Germany, 1:200k | Same BGR ArcGIS REST pattern as BÜK200 | Pairs with soil data for the "geology vs soil texture" overlay visualisation |
| **LAiV / LUNG M-V (BOSIS, soil geology)** | Bodenzahl, nFK, rooting depth, peat | Mecklenburg-Vorpommern | State geoportal WMS/WFS | Only if you want a second state to prove extendability — otherwise a distraction. I'd keep the hackathon anchored on Niedersachsen |
| **NASA EMIT** | Topsoil mineralogy | Global, 60 m | Earthdata | Cool but hard to turn into an agronomic number in a day; "bonus points" territory at most |

You can register for a free non-commercial account for Google Earth Engine which provides a bunch of great datasets, an easy API to work with a distributed environment for computing/manipulating large raster imagery datasets. 

* Sign up is here: [https\://code.earthengine.google.com/register](https://code.earthengine.google.com/register)  
* Their soil relevant datasets can be found here: [https\://developers.google.com/earth-engine/datasets/tags/soil](https://developers.google.com/earth-engine/datasets/tags/soil)  
* Access to raw Sentinel 1 and Sentinel 2 data is also hosted on Earth Engine and in my experience way easier to interact with in Earth Engine that directly from the European Copernicus servers  
  * [https\://developers.google.com/earth-engine/datasets/catalog/COPERNICUS\_S1\_GRD](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD)  
  * [https\://developers.google.com/earth-engine/datasets/catalog/COPERNICUS\_S2\_SR\_HARMONIZED](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED)