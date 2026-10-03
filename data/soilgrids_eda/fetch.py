# /// script
# dependencies = ["requests", "pandas"]
# ///
import requests, pandas as pd, time, json
URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"
PROPS = ['bdod','cec','cfvo','clay','nitrogen','ocd','ocs','phh2o','sand','silt','soc','wv0010','wv0033','wv1500']
DEPTHS = ["0-5cm","5-15cm","15-30cm","30-60cm","60-100cm","100-200cm","0-30cm"]
STATS = ["Q0.05","Q0.5","Q0.95","mean","uncertainty"]
SITES = {
  "Hildesheimer Börde (loess)": (9.95, 52.12),
  "Lüneburger Heide (sand)":    (10.05, 53.05),
  "Emsland (sand/peat)":        (7.35, 52.75),
  "Wesermarsch (marsh clay)":   (8.40, 53.35),
  "Teufelsmoor (bog)":          (8.90, 53.25),
  "Solling (upland forest)":    (9.55, 51.75),
  "Hannover centre (urban)":    (9.73, 52.37),
}

def query(lon, lat, props):
    params = [("lon", lon), ("lat", lat)] + [("property", p) for p in props] \
           + [("depth", d) for d in DEPTHS] + [("value", v) for v in STATS]
    for _ in range(4):
        try:
            r = requests.get(URL, params=params, timeout=300)
            if r.status_code == 200:
                return r.json()
            print("http", r.status_code, flush=True)
        except requests.exceptions.RequestException as e:
            print("err", e.__class__.__name__, flush=True)
        time.sleep(15)
    raise RuntimeError("gave up")

rows, meta = [], {}
for site, (lon, lat) in SITES.items():
    for chunk in [PROPS[i:i+5] for i in range(0, len(PROPS), 5)]:
        t0 = time.time()
        js = query(lon, lat, chunk)
        print(site, chunk, "wall", round(time.time() - t0, 1), flush=True)
        for layer in js["properties"]["layers"]:
            um = layer["unit_measure"]; meta[layer["name"]] = um
            for d in layer["depths"]:
                for k, v in d["values"].items():
                    # uncertainty is (Q95-Q05)/Q50 * 10 -> divide by 10 for a ratio
                    val = None if v is None else v / (10 if k == "uncertainty" else um["d_factor"])
                    rows.append(dict(site=site, lon=lon, lat=lat, prop=layer["name"], depth=d["label"],
                                     stat=k, raw=v, value=val, unit=um["target_units"]))
        time.sleep(3)
pd.DataFrame(rows).to_csv("soilgrids_sites.csv", index=False)
json.dump(meta, open("units.json", "w"), indent=1)
print("done", len(rows))
