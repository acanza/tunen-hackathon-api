# /// script
# requires-python = ">=3.11"
# dependencies = ["rasterio", "numpy", "geopandas", "matplotlib", "scipy"]
# ///
"""Quicklook of the terrain covariates with field outlines.

    uv run poc/quicklook_dem.py      # after build_store.py; writes covariates/quicklook_dem.png
"""
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import rasterio
from scipy.ndimage import gaussian_filter

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COV = ROOT / "poc" / "store" / "runs" / "poc-2026-10-03" / "covariates"

# one hue per magnitude layer, a two-pole diverging map for relative elevation
PANELS = {
    "elev": ("Elevation (m)", "Greys", None),
    "slope": ("Slope (°), smoothed", "Oranges", (0, 4)),
    "twi": ("Wetness index (TWI)", "Blues", (6, 13)),
    "rel_elev": ("Relative elevation (m)", "RdBu", (-6, 6)),
}

with rasterio.open(COV / "dem__copernicus.tif") as src:
    bands = {n: src.read(i + 1) for i, n in enumerate(src.descriptions)}
    b = src.bounds
# grey out areas with no measured ground within a few hundred metres (pure interpolation)
supported = gaussian_filter(bands["ground_mask"], 10) > 0.05
fields = gpd.read_file(ROOT / "data" / "seggerde" / "clean" / "fields_clean.geojson").to_crs(32632)

fig, axes = plt.subplots(1, 4, figsize=(18, 6), constrained_layout=True)
for ax, (key, (title, cmap, lim)) in zip(axes, PANELS.items()):
    a = np.where(supported, bands[key], np.nan)
    vmin, vmax = lim or np.nanpercentile(a, [1, 99])
    ax.set_facecolor("#e6e6e6")
    im = ax.imshow(a, cmap=cmap, vmin=vmin, vmax=vmax, extent=(b.left, b.right, b.bottom, b.top))
    fields.boundary.plot(ax=ax, color="#222222", linewidth=0.5)
    ax.set_title(title, fontsize=11, color="#222222")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.colorbar(im, ax=ax, orientation="horizontal", fraction=0.04, pad=0.02).outline.set_visible(False)
fig.suptitle("Seggerde terrain on the 10 m grid: ground from field interiors (Copernicus GLO-30), grey = no ground data nearby", fontsize=12, color="#222222")
out = COV / "quicklook_dem.png"
fig.savefig(out, dpi=110)
print(out)
