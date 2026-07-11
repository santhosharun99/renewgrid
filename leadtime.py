"""Lead-time skill evaluation + horizon-aware band calibration.

Replays history through the EXACT serving chain: what the weather forecast
said d days in advance (Open-Meteo previous-runs archive) -> physics ->
saved quantile boosters -> compare against actual production. This
measures, per lead day 1..7:
  - daily kWh MAPE of the served forecast (and pvlib-only)
  - raw P10-P90 coverage (train/serve skew shows up here)
  - a split-conformal widening Q_d, saved to leadtime_calibration.json,
    which export_forecast.py applies so bands GROW with horizon.

Limitation: air-quality features use observed history (no archived AQ
forecasts) - AQ carries ~7% of attribution, so lead-day skill is very
slightly optimistic. Run: python leadtime.py [--fetch]
"""
import json
import os
import sys

import numpy as np
import pandas as pd
import requests
import lightgbm as lgb

import dataset
import physics
import quality

VARS = ["shortwave_radiation", "direct_normal_irradiance",
        "diffuse_radiation", "temperature_2m", "cloud_cover",
        "wind_speed_10m", "precipitation"]
LEADS = [1, 2, 3, 5, 7]
CACHE = "leadtime_weather.csv"
FEAT = dataset.BASE_FEAT + dataset.AQ_FEAT + dataset.SPATIAL_FEAT


def fetch():
    df = pd.read_parquet("production.parquet")
    d0, d1 = df.t.min().date(), df.t.max().date()
    frames = []
    for d in LEADS:
        print(f"fetching previous_day{d} forecasts {d0} -> {d1} ...")
        r = requests.get("https://previous-runs-api.open-meteo.com/v1/forecast",
                         params={"latitude": physics.LAT, "longitude": physics.LON,
                                 "hourly": ",".join(f"{v}_previous_day{d}" for v in VARS),
                                 "start_date": str(d0), "end_date": str(d1),
                                 "timezone": physics.TZ}, timeout=300)
        r.raise_for_status()
        h = pd.DataFrame(r.json()["hourly"])
        h["time"] = pd.to_datetime(h["time"])
        frames.append(h.set_index("time"))
    out = pd.concat(frames, axis=1)
    out.to_csv(CACHE)
    print(f"saved {CACHE}  rows {len(out)}")


def build_lead_frame(w_lead, d):
    """Feature frame from the day-d forecast weather, mirroring dataset.build."""
    j = w_lead.rename(columns={f"{v}_previous_day{d}": v for v in VARS}).copy()
    j = j.dropna(subset=["shortwave_radiation"])
    j = j.join(physics.load_aq(), how="left")          # observed AQ (see docstring)
    # spatial disagreement from the archived (final-run) grid - an
    # approximation of what the day-d forecast grid would have shown
    sp = pd.read_csv("spatial.csv", parse_dates=["time"]).set_index("time")
    sp.index = sp.index.tz_localize(physics.TZ)
    j = j.join(sp, how="left")
    exp = physics.expected(j)
    j["pvlib"] = exp["ac"]; j["poa"] = exp["poa"]
    j["poa_direct"] = exp["poa_direct"]
    j["zenith"] = exp["zenith"]; j["azimuth"] = exp["azimuth"]
    j["hour"] = j.index.hour + j.index.minute / 60
    doy = j.index.dayofyear
    j["doy_sin"] = np.sin(2 * np.pi * doy / 365)
    j["doy_cos"] = np.cos(2 * np.pi * doy / 365)
    j["clearness"] = (j.shortwave_radiation / (j.poa + 1)).clip(0, 2)
    return j[j.poa > 20]


def main():
    if "--fetch" in sys.argv or not os.path.exists(CACHE):
        fetch()
    wl = pd.read_csv(CACHE, parse_dates=["time"]).set_index("time")
    wl.index = wl.index.tz_localize(physics.TZ)

    raw = quality.load_production()
    ph = raw.set_index("t")["power_w"].resample("h").mean()
    ph.index = ph.index.tz_localize(physics.TZ)
    good = quality.usable_days(raw) - quality.event_days()

    boosters = {n: lgb.Booster(model_file=f"{n}.txt") for n in ("m10", "m50", "m90")}
    calib, rows = {}, []
    for d in LEADS:
        j = build_lead_frame(wl, d)
        j["p"] = ph.reindex(j.index)
        j = j.dropna(subset=["p"])
        j = quality.keep_days(j, good)
        preds = {n: (j.pvlib + b.predict(j[FEAT])).clip(lower=0)
                 for n, b in boosters.items()}
        lo = np.minimum(preds["m10"], preds["m90"])
        hi = np.maximum(preds["m10"], preds["m90"])

        a = j.p.resample("D").sum().dropna() / 1000
        a = a[a > 0]
        f50 = preds["m50"].resample("D").sum().reindex(a.index) / 1000
        fpv = j.pvlib.resample("D").sum().reindex(a.index) / 1000
        cov = float(((j.p >= lo) & (j.p <= hi)).mean())

        # split-conformal widening on the first 70% of days; report
        # calibrated coverage on the last 30% (honest holdout)
        days = sorted({ts.date() for ts in j.index})
        cutoff = days[int(len(days) * 0.7)]
        cal_m = np.array([ts.date() <= cutoff for ts in j.index])
        scores = np.maximum(lo[cal_m] - j.p[cal_m], j.p[cal_m] - hi[cal_m])
        n = len(scores)
        q = float(np.quantile(scores, min(1.0, np.ceil(0.8 * (n + 1)) / n)))
        te = ~cal_m
        ccov = float(((j.p[te] >= lo[te] - q) & (j.p[te] <= hi[te] + q)).mean())
        calib[str(d)] = round(q, 1)

        rows.append(dict(lead_day=d, n_days=len(a),
                         mape_hybrid=round(float((abs(a - f50) / a).mean() * 100), 2),
                         mape_pvlib=round(float((abs(a - fpv) / a).mean() * 100), 2),
                         raw_cov=round(cov * 100, 1),
                         conf_widen_W=round(q, 1),
                         conf_cov_holdout=round(ccov * 100, 1)))

    r = pd.DataFrame(rows).set_index("lead_day")
    print("\n=== skill by forecast lead day (served chain, vs actual) ===")
    print(r.to_string())
    with open("leadtime_calibration.json", "w") as f:
        json.dump(calib, f, indent=1)
    print("\nsaved leadtime_calibration.json (band widening per lead day, W)")


if __name__ == "__main__":
    main()
