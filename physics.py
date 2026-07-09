"""The pvlib physics layer — the 'pretrained model' for this plant.

Single source of truth for plant constants and the weather->power chain,
shared by model.py, backtest.py, outage_classifier.py. Calibrated
parameters (Task 7) live in params.json; hardcoded values below are the
fallback when it doesn't exist.
"""
import json
import os
import pandas as pd
import pvlib

LAT, LON, TZ = 10.7905, 78.7047, "Asia/Kolkata"

DEFAULTS = dict(tilt=10.0, azim=105.0, pdc0=2674.0, gamma=-0.0035,
                temp_model="sapm", shade_horizon=0.0, pac0=5000.0,
                inverter=False)


def params(path="params.json"):
    p = dict(DEFAULTS)
    if os.path.exists(path):
        p.update(json.load(open(path)))
    return p


def load_weather(path="weather_all.csv"):
    w = pd.read_csv(path, parse_dates=["time"]).set_index("time")
    if w.index.tz is None:
        w.index = w.index.tz_localize(TZ)
    return w


def load_aq(path="aq_all.csv"):
    aq = pd.read_csv(path, parse_dates=["time"]).set_index("time")
    if aq.index.tz is None:
        aq.index = aq.index.tz_localize(TZ)
    return aq


def load_production_hourly(path="production.parquet"):
    df = pd.read_parquet(path)
    ph = df.set_index("t")["power_w"].resample("h").mean()
    ph.index = ph.index.tz_localize(TZ)
    return ph


def cell_temperature(poa, w, model="sapm"):
    if model == "sapm":
        return pvlib.temperature.sapm_cell(
            poa, w.temperature_2m, w.wind_speed_10m,
            **pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS
            ["sapm"]["open_rack_glass_polymer"])
    if model == "faiman":
        return pvlib.temperature.faiman(poa, w.temperature_2m, w.wind_speed_10m)
    if model == "pvsyst":
        return pvlib.temperature.pvsyst_cell(poa, w.temperature_2m,
                                             w.wind_speed_10m)
    raise ValueError(model)


def expected(w, p=None, sp=None):
    """Weather dataframe -> dict of hourly series: ac (W), poa, poa_direct,
    zenith, azimuth. Index = w.index (tz-aware). Pass a precomputed
    solarposition frame via sp when calling repeatedly (calibration)."""
    p = p or params()
    if sp is None:
        sp = pvlib.solarposition.get_solarposition(w.index, LAT, LON)
    poa = pvlib.irradiance.get_total_irradiance(
        p["tilt"], p["azim"], sp.apparent_zenith, sp.azimuth,
        dni=w.direct_normal_irradiance, ghi=w.shortwave_radiation,
        dhi=w.diffuse_radiation,
        dni_extra=pvlib.irradiance.get_extra_radiation(w.index),
        model="haydavies")
    poa_global = poa.poa_global.copy()

    # eastern-house shading: below this solar elevation while the sun is in
    # the east, direct POA is blocked and only diffuse survives
    if p["shade_horizon"] > 0:
        elev = 90.0 - sp.apparent_zenith
        shaded = (elev < p["shade_horizon"]) & (sp.azimuth < 180)
        poa_global = poa_global.where(~shaded, poa.poa_diffuse)

    tcell = cell_temperature(poa_global, w, p["temp_model"])
    dc = pvlib.pvsystem.pvwatts_dc(poa_global, tcell,
                                   p["pdc0"], p["gamma"]).clip(lower=0)
    if p.get("inverter"):
        ac = pvlib.inverter.pvwatts(dc, p["pac0"]).clip(lower=0).fillna(0)
    else:
        ac = dc
    return dict(ac=ac, poa=poa_global, poa_direct=poa.poa_direct,
                zenith=sp.apparent_zenith, azimuth=sp.azimuth)
