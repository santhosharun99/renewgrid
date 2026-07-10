"""Real tomorrow forecast.

Fetches TOMORROW's hourly weather + air-quality forecasts from Open-Meteo,
builds the same feature frame the models were trained on (dataset.py),
runs the physics layer + saved quantile boosters (m10/m50/m90.txt), and
writes forecast.json.

The old version predicted the last *historical* day — a hindcast wearing a
forecast's clothes. This one actually looks forward.

Run standalone (python export_forecast.py [YYYY-MM-DD]) or via
generate(day); api.py regenerates lazily when the file is stale.
"""
import json
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests
import lightgbm as lgb

import dataset
import physics

FEAT = dataset.BASE_FEAT + dataset.AQ_FEAT
HOURLY_W = ("shortwave_radiation,direct_normal_irradiance,diffuse_radiation,"
            "temperature_2m,cloud_cover,wind_speed_10m,precipitation")
HOURLY_AQ = "pm10,pm2_5,aerosol_optical_depth,dust"


def _fetch(url, hourly, day):
    r = requests.get(url, params={
        "latitude": physics.LAT, "longitude": physics.LON,
        "hourly": hourly, "timezone": physics.TZ,
        "start_date": str(day), "end_date": str(day)}, timeout=20)
    r.raise_for_status()
    df = pd.DataFrame(r.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])
    df = df.set_index("time")
    df.index = df.index.tz_localize(physics.TZ)
    return df


def generate(day=None):
    day = day or date.today() + timedelta(days=1)
    w = _fetch("https://api.open-meteo.com/v1/forecast", HOURLY_W, day)
    aq = _fetch("https://air-quality-api.open-meteo.com/v1/air-quality",
                HOURLY_AQ, day)
    j = w.join(aq, how="left").ffill().bfill()

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
    # quantile crossing guard
    stacked = np.sort(np.vstack([preds["m10"], preds["m50"], preds["m90"]]),
                      axis=0)
    out = [{"time": ts.strftime("%H:%M"),
            "p10": float(stacked[0, i]),
            "p50": float(stacked[1, i]),
            "p90": float(stacked[2, i])}
           for i, ts in enumerate(j.index)]
    doc = {"date": str(day),
           "generated_at": datetime.now().isoformat(timespec="seconds"),
           "hourly": out}
    with open("forecast.json", "w") as f:
        json.dump(doc, f)
    return doc


if __name__ == "__main__":
    day = pd.to_datetime(sys.argv[1]).date() if len(sys.argv) > 1 else None
    d = generate(day)
    kwh = sum(h["p50"] for h in d["hourly"]) / 1000
    print(f"forecast for {d['date']}: p50 {kwh:.1f} kWh "
          f"({len(d['hourly'])} daylight hours) -> forecast.json")
