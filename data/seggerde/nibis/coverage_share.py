# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "geopandas", "rasterio", "pandas"]
# ///
"""Share of each field's area covered by NIBIS polygons, from the GetMap images (drawn = alpha > 0).
Adds L816_area_share / L849_area_share to nibis_fields.csv. Run after fetch_nibis.py."""
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from PIL import Image
from rasterio.features import rasterize
from rasterio.transform import from_bounds

HERE = Path(__file__).parent
x0, y0, x1, y1 = (float(v) for v in (HERE / "bbox_25832.txt").read_text().split(","))
f = gpd.read_file(HERE.parent / "clean" / "fields_clean.geojson").to_crs(25832)
res = pd.read_csv(HERE / "nibis_fields.csv")
for layer in ("L816", "L849"):
    alpha = np.array(Image.open(HERE / "raw" / f"getmap_{layer}.png").convert("RGBA"))[..., 3] > 0
    h, w = alpha.shape
    tf = from_bounds(x0, y0, x1, y1, w, h)
    share = {}
    for pid, geom in zip(f.plotId, f.geometry):
        m = rasterize([(geom, 1)], out_shape=(h, w), transform=tf, all_touched=False).astype(bool)
        share[pid] = float(alpha[m].mean()) if m.any() else np.nan
    res[f"{layer}_area_share"] = res.plotId.map(share).round(3)
res.to_csv(HERE / "nibis_fields.csv", index=False)
print(res[["fieldName", "L816_area_share", "L849_area_share", "L816_status"]]
      .query("L816_area_share > 0").sort_values("L816_area_share").to_string(index=False))
a = f.set_index("plotId").area / 1e4
for layer in ("L816", "L849"):
    s = res.set_index("plotId")[f"{layer}_area_share"].fillna(0)
    print(f"{layer}: covered area {float((s * a).sum()):.1f} ha of {a.sum():.1f}; fields fully (>95%) {int((s > .95).sum())}, partly {int(((s > .05) & (s <= .95)).sum())}, none {int((s <= .05).sum())}")
