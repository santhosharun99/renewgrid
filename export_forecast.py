"""7-day generation forecast.

Fetches hourly weather + air-quality *forecasts* from Open-Meteo for the
next week, builds the same feature frame the models were trained on
(dataset.py), runs the physics layer + saved quantile boosters
(m10/m50/m90.txt), and writes forecast.json with one entry per day.

Trained on reanalysis weather, driven here by forecast weather - so
uncertainty grows with horizon; day 6 is genuinely less certain than
tomorrow. api.py regenerates lazily when the file is >4 h old (weather
models refresh every few hours).

Run standalone: python export_forecast.py [days]
"""
import json
import os
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests
import lightgbm as lgb

import dataset
import physics

FEAT = dataset.BASE_FEAT + dataset.AQ_FEAT + dataset.SPATIAL_FEAT
HOURLY_W = ("shortwave_radiation,direct_normal_irradiance,diffuse_radiation,"
            "temperature_2m,cloud_cover,wind_speed_10m,precipitation")
HOURLY_AQ = "pm10,pm2_5,aerosol_optical_depth,dust"
SPATIAL_VARS = {"cloud_cover": "cc", "shortwave_radiation": "ghi",
                "temperature_2m": "t"}
GRID_D = 0.35   # deg spacing - distinct NWP cells (see fetch_spatial.py)
# fallback when the AQ forecast doesn't reach the full horizon
AQ_DEFAULT = {"pm10": 25.0, "pm2_5": 12.0, "aerosol_optical_depth": 0.2, "dust": 5.0}


def _fetch(url, hourly, d0, d1):
    r = requests.get(url, params={
        "latitude": physics.LAT, "longitude": physics.LON,
        "hourly": hourly, "timezone": physics.TZ,
        "start_date": str(d0), "end_date": str(d1)}, timeout=25)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time")
    df.index = df.index.tz_localize(physics.TZ)
    return df


def _fetch_spatial(d0, d1):
    """3x3-grid NWP-disagreement features from the forecast API (same
    construction as fetch_spatial.py, forecast-time edition)."""
    lats, lons = [], []
    for dy in (-GRID_D, 0, GRID_D):
        for dx in (-GRID_D, 0, GRID_D):
            lats.append(round(physics.LAT + dy, 4))
            lons.append(round(physics.LON + dx, 4))
    r = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": ",".join(map(str, lats)), "longitude": ",".join(map(str, lons)),
        "hourly": ",".join(SPATIAL_VARS), "timezone": physics.TZ,
        "start_date": str(d0), "end_date": str(d1)}, timeout=30)
    r.raise_for_status()
    cells = r.json()
    time = pd.to_datetime(cells[0]["hourly"]["time"])
    out = pd.DataFrame(index=time)
    for v, s in SPATIAL_VARS.items():
        m = np.array([c["hourly"][v] for c in cells], dtype=float)
        out[f"{s}_std"] = np.nanstd(m, axis=0)
        out[f"{s}_maxd"] = np.nanmax(np.abs(m - m[4]), axis=0)
    out.index = out.index.tz_localize(physics.TZ)
    return out


def generate(days=7):
    d0 = date.today()
    d1 = d0 + timedelta(days=days - 1)
    w = _fetch("https://api.open-meteo.com/v1/forecast", HOURLY_W, d0, d1)
    try:
        aq = _fetch("https://air-quality-api.open-meteo.com/v1/air-quality",
                    HOURLY_AQ, d0, d1)
        j = w.join(aq, how="left")
    except Exception:
        j = w.copy()
        for c in AQ_DEFAULT:
            j[c] = np.nan
    for c, v in AQ_DEFAULT.items():
        j[c] = j[c].ffill().bfill().fillna(v)
    try:
        j = j.join(_fetch_spatial(d0, d1), how="left")
    except Exception:
        for c in dataset.SPATIAL_FEAT:
            j[c] = np.nan   # LightGBM handles missing natively
    j = j.dropna(subset=["shortwave_radiation"])

    exp = physics.expected(j)
    j["pvlib"] = exp["ac"]
    j["poa"] = exp["poa"]
    j["poa_direct"] = exp["poa_direct"]
    j["zenith"] = exp["zenith"]
    j["azimuth"] = exp["azimuth"]
    j["hour"] = j.index.hour + j.index.minute / 60
    doy = j.index.dayofyear
    j["doy_sin"] = np.sin(2 * np.pi * doy / 365)
    j["doy_cos"] = np.cos(2 * np.pi * doy / 365)
    j["clearness"] = (j.shortwave_radiation / (j.poa + 1)).clip(0, 2)

    j = j[j.poa > 20]  # models are trained on daylight rows only
    preds = {}
    for name in ("m10", "m50", "m90"):
        b = lgb.Booster(model_file=f"{name}.txt")
        preds[name] = (j.pvlib + b.predict(j[FEAT])).clip(lower=0)
    stacked = np.sort(np.vstack([preds["m10"], preds["m50"], preds["m90"]]),
                      axis=0)  # quantile crossing guard

    # horizon-aware honesty: widen P10-P90 by the split-conformal offset
    # measured per lead day against archived past forecasts (leadtime.py).
    # Without this, day 6 wears day 1's confidence.
    try:
        with open("leadtime_calibration.json") as f:
            _cal = {int(k): float(v) for k, v in json.load(f).items()}
    except Exception:
        _cal = {}

    def _widen(lead):
        if not _cal:
            return 0.0
        ks = sorted(_cal)
        k = min(max(lead, ks[0]), ks[-1])
        if k in _cal:
            return _cal[k]
        below = max(x for x in ks if x < k)
        above = min(x for x in ks if x > k)
        frac = (k - below) / (above - below)
        return _cal[below] + frac * (_cal[above] - _cal[below])

    out_days = []
    today = date.today()
    for day, idx in pd.Series(range(len(j)), index=j.index).groupby(j.index.date):
        rows = idx.values
        q = _widen((day - today).days)
        hourly = [{"time": ts.strftime("%H:%M"),
                   "p10": float(max(0.0, stacked[0, i] - q)),
                   "p50": float(stacked[1, i]),
                   "p90": float(stacked[2, i] + q)}
                  for i, ts in zip(rows, j.index[rows])]
        out_days.append({
            "date": str(day),
            "weekday": pd.Timestamp(day).strftime("%a"),
            "p10_kwh": round(float(stacked[0, rows].sum()) / 1000, 2),
            "p50_kwh": round(float(stacked[1, rows].sum()) / 1000, 2),
            "p90_kwh": round(float(stacked[2, rows].sum()) / 1000, 2),
            "hourly": hourly,
        })
    doc = {"generated_at": datetime.now().isoformat(timespec="seconds"),
           "days": out_days}
    with open("forecast.json", "w") as f:
        json.dump(doc, f)
    # archive every issued forecast so future skill claims can be scored
    # against our own operational record, not a reconstruction
    os.makedirs("forecasts", exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    with open(f"forecasts/forecast_{stamp}.json", "w") as f:
        json.dump(doc, f)
    return doc


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    d = generate(n)
    for day in d["days"]:
        print(f"{day['date']} ({day['weekday']}): p50 {day['p50_kwh']:5.1f} kWh"
              f"   [{day['p10_kwh']:.1f} – {day['p90_kwh']:.1f}]")
