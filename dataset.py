"""Hourly modeling dataset: production joined to weather (+air quality),
physics expectation, engineered features. Shared by model.py, backtest.py,
shap_attribution.py so they can't drift apart.
"""
import numpy as np
import pandas as pd

import physics
import quality

BASE_FEAT = ["pvlib", "poa", "poa_direct", "shortwave_radiation",
             "direct_normal_irradiance", "diffuse_radiation", "temperature_2m",
             "cloud_cover", "wind_speed_10m", "precipitation", "hour",
             "doy_sin", "doy_cos", "zenith", "azimuth", "clearness"]
AQ_FEAT = ["pm10", "pm2_5", "aerosol_optical_depth", "dust"]


def build(include_aq=True, exclude_events=True, daylight_poa=20):
    """-> (j, feat): hourly frame with p (actual W), pvlib (expected W),
    target (residual) and feature columns; daylight rows on usable,
    non-event days only."""
    raw = quality.load_production()
    ph = raw.set_index("t")["power_w"].resample("h").mean()
    ph.index = ph.index.tz_localize(physics.TZ)

    w = physics.load_weather()
    j = pd.DataFrame({"p": ph}).join(w, how="inner")

    feat = list(BASE_FEAT)
    if include_aq:
        j = j.join(physics.load_aq(), how="left")
        feat += AQ_FEAT

    exp = physics.expected(j)
    j["pvlib"] = exp["ac"]
    j["poa"] = exp["poa"]
    j["poa_direct"] = exp["poa_direct"]
    j["zenith"] = exp["zenith"]
    j["azimuth"] = exp["azimuth"]

    j = quality.keep_days(j, quality.usable_days(raw))
    if exclude_events:
        j = quality.exclude_events(j)

    j = j[j.poa > daylight_poa]
    j["hour"] = j.index.hour + j.index.minute / 60
    j["doy"] = j.index.dayofyear
    j["doy_sin"] = np.sin(2 * np.pi * j.doy / 365)
    j["doy_cos"] = np.cos(2 * np.pi * j.doy / 365)
    j["clearness"] = (j.shortwave_radiation / (j.poa + 1)).clip(0, 2)
    j["target"] = j.p - j.pvlib
    return j.dropna(subset=["p", "pvlib"] + BASE_FEAT), feat


def hourly_actual_all_days(raw=None):
    """Hourly production incl. event days (persistence baseline donor pool),
    restricted to days with enough samples to trust the profile."""
    if raw is None:
        raw = quality.load_production()
    ph = raw.set_index("t")["power_w"].resample("h").mean()
    ph.index = ph.index.tz_localize(physics.TZ)
    return quality.keep_days(ph, quality.usable_days(raw)).fillna(0)
