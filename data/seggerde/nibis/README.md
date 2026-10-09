# NIBIS (LBEG) coverage of the Seggerde farm

**The farm straddles the Niedersachsen / Sachsen-Anhalt border.** The western fields (around Mackendorf, Saalsdorf, Bredau; lon < ~11.06) are in Niedersachsen and have full BK50 and Bodenschätzung data. The eastern fields are in Sachsen-Anhalt, which NIBIS doesn't cover.

```
uv run fetch_nibis.py        # GetMap coverage images, then GetFeatureInfo per covered field (slow, patient)
uv run coverage_share.py     # area share per field covered, from the GetMap images
```

## Coverage

| | BK50 (L816) | Bodenschätzung (L849) |
|---|---|---|
| Fields fully covered (> 95 % of area) | 39 | 40 |
| Partly covered | 2 (`Silbersee` 21 %, `Saalsdorfer Breite` 2 %) | 0 |
| Not covered | 46 | 47 |
| Covered area | 240.8 ha of 883.5 | 238.1 ha |

The border runs almost exactly along field edges, so nearly every field is either fully in or fully out.

## Values (one point per field)

Queried at each field's representative point (from `../clean/fields_clean.geojson`) with a 10 m box in EPSG:25832. Raw GeoJSON is in `raw/gfi_<layer>_<plotId>.json`; the flattened values are in `nibis_fields.csv`.

- **Soil types (BK50):** Gley, Podsol-Gley, Gley-Podsol, Podsol-Braunerde, Gley-Braunerde, Gley-Vega. Sandy soils with groundwater influence, consistent with BÜK200's units for this area.
- **Land use (`NUTZUNG`):** A (arable) everywhere, except FL at `Papenberg Brache`.
- **Bodenzahl / Ackerzahl: 17–49**, mostly 18–40. These are **poor soils** by German standards; the Hildesheim Börde test site was 71–90.
  - Lowest (17–20): `Kurze Enden vor Biogas`, `Tomatenacker`, `Warberg`, `Klapperberg`, `Springphör`, `Umfeld Groß/Klein`. Klassenzeichen S5D / S4D: sand, poorest condition class.
  - Highest (41–49): the floodplain fields around Nachthude (`Rohwiese` 49/50, `Nachthude 2` 48/48, `Schäferberg`, `Allerwiese`). Klassenzeichen lS4Al: loamy sand on alluvium.
- **Point values only.** Bodenschätzung parcels are mapped at 1:5k and a field can contain several. One point per field gives one value; area-weighted values would need the Bodenschätzung polygons (GetFeatureInfo returns them, or sample several points per field as we did for BÜK200).

## Server behaviour (important for the API)

- **Server-wide concurrent request limit.** When it's hit, the server answers **HTTP 200** with a `ServiceExceptionReport` containing `Error 503.2 - Concurrent request limit exceeded`. Requests can also hang (60 s timeouts). Check the body, not just the status code.
- This run: GetMap was busy for ~13 minutes (3 attempts), then succeeded in 16–35 s. GetFeatureInfo mostly took 0.3–0.6 s, with occasional 15–36 s responses and a few 60 s timeouts that succeeded on retry. See `request_log.csv`.
- Rules that worked: one request at a time, 60 s timeout, back off 1–6 minutes on 503.2, 2 s pause between requests, and stop after 3 failures in a row.
- For production, query NIBIS once per field and cache. Never call it from a user request path.

## Files

| File | Content |
|---|---|
| `fetch_nibis.py`, `coverage_share.py` | Scripts |
| `nibis_fields.csv` | Per field: coverage share per layer, status, soil type, land use, Bodenzahl, Ackerzahl, Klassenzeichen |
| `raw/getmap_L816.png`, `raw/getmap_L849.png` | Coverage images over the farm (transparent = no data) |
| `raw/gfi_*.json` | Untouched GetFeatureInfo responses |
| `request_log.csv` | Every request with status, busy flag, duration |
| `bbox_25832.txt` | Image extent (EPSG:25832) |
