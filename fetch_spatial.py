"""Spatial instability features: query a 3x3 grid of points around the
site (0.35 deg ~ 39 km spacing - wide enough that points fall in distinct
NWP model cells; tighter grids sample one cell and give zero variance).

Per hour, for cloud cover / GHI / temperature: the standard deviation
across the 9 cells and the max |center - neighbor| delta. High disagreement
= unstable local atmosphere = wider honest uncertainty.

Writes spatial.csv consumed by dataset.build(include_spatial=True).
"""
import numpy as np
import pandas as pd
import requests

import physics

D = 0.35
VARS = ["cloud_cover", "shortwave_radiation", "temperature_2m"]
SHORT = {"cloud_cover": "cc", "shortwave_radiation": "ghi", "temperature_2m": "t"}

lats, lons = [], []
for dy in (-D, 0, D):
    for dx in (-D, 0, D):
        lats.append(round(physics.LAT + dy, 4))
        lons.append(round(physics.LON + dx, 4))
CENTER = 4  # index of the site cell

df = pd.read_parquet("production.parquet")
d0, d1 = df.t.min().date(), df.t.max().date()
print(f"fetching 9-cell grid {d0} -> {d1} ...")

r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
    "latitude": ",".join(map(str, lats)), "longitude": ",".join(map(str, lons)),
    "start_date": str(d0), "end_date": str(d1),
    "hourly": ",".join(VARS), "timezone": "Asia/Kolkata"}, timeout=300)
r.raise_for_status()
cells = r.json()
assert len(cells) == 9, f"expected 9 cells, got {len(cells)}"

time = pd.to_datetime(cells[0]["hourly"]["time"])
out = pd.DataFrame({"time": time})
for v in VARS:
    m = np.array([c["hourly"][v] for c in cells], dtype=float)  # 9 x T
    s = SHORT[v]
    out[f"{s}_std"] = np.nanstd(m, axis=0)
    out[f"{s}_maxd"] = np.nanmax(np.abs(m - m[CENTER]), axis=0)

out.to_csv("spatial.csv", index=False)
uniq = {v: len(np.unique(np.array([c["hourly"][v] for c in cells])[:, 12]))
        for v in VARS}
print(f"saved spatial.csv  rows {len(out)}")
print("distinct values across 9 cells at hour 12 (sanity - should be >1):", uniq)
