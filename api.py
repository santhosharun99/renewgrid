from fastapi import FastAPI, HTTPException
import sqlite3
import pandas as pd
import numpy as np
import pvlib
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import requests
from datetime import date, datetime, timedelta

import tneb

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

LAT, LON, TZ = 10.7905, 78.7047, "Asia/Kolkata"
TILT, AZIM   = 10.0, 105.0
PDC0, GAMMA  = 2674, -0.0035

# ── Config (can be user-adjusted later) ──────────────────────────────
TARIFF_RS_PER_KWH    = 7.0      # Effective rate saved per kWh (TANGEDCO offset)
INSTALL_COST_RS      = 180000   # Approx install cost ₹1,80,000 for 3 kWp
CO2_KG_PER_KWH       = 0.82     # India grid emission factor (CEA 2022-23)
CO2_PER_TREE_PER_YR  = 22.0     # kg CO₂ a mature tree absorbs per year

# ── Cache ─────────────────────────────────────────────────────────────
_df_hist = None
_hist_mtime = None
_weather_df = None

def get_hist():
    global _df_hist, _hist_mtime
    m = os.path.getmtime("production.parquet")
    if _df_hist is None or m != _hist_mtime:
        _df_hist = pd.read_parquet("production.parquet")
        _df_hist['t'] = pd.to_datetime(_df_hist['t'])
        _hist_mtime = m
    return _df_hist

def live_readings(day=None):
    """Rows the LSW-3 logger wrote to solar.db for `day` (default: actual
    today), shaped like production history. The app export only covers up
    to yesterday; today comes from here."""
    day = day or date.today()
    try:
        con = sqlite3.connect("solar.db")
        df = pd.read_sql(
            "SELECT ts, ac_power, yield_today FROM readings WHERE ts LIKE ?",
            con, params=(f"{day}%",))
        con.close()
    except Exception:
        return pd.DataFrame(columns=["t", "power_w", "yield_today"])
    df["t"] = pd.to_datetime(df["ts"])
    df["power_w"] = df["ac_power"].astype(float)
    return df[["t", "power_w", "yield_today"]].sort_values("t")

def get_full():
    """Production history + live logger rows newer than the parquet."""
    h = get_hist()
    lv = live_readings()
    lv = lv[lv["t"] > h["t"].max()]
    if len(lv):
        return pd.concat([h, lv[["t", "power_w"]]], ignore_index=True)
    return h

def get_weather_df():
    global _weather_df
    if _weather_df is None:
        _weather_df = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time")
        _weather_df.index = _weather_df.index.tz_localize(TZ)
    return _weather_df

_wx_recent = None
_wx_recent_at = 0.0

def get_weather_recent():
    """Hourly weather for the last few days incl. today, from the
    Open-Meteo forecast API. weather_all.csv (archive API) lags several
    days, so without this the physics prediction is 0 for today."""
    global _wx_recent, _wx_recent_at
    import time as _time
    if _wx_recent is None or _time.time() - _wx_recent_at > 1800:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "shortwave_radiation,direct_normal_irradiance,"
                      "diffuse_radiation,temperature_2m,cloud_cover,"
                      "wind_speed_10m,precipitation",
            "timezone": TZ, "past_days": 7, "forecast_days": 1}, timeout=20)
        r.raise_for_status()
        w = pd.DataFrame(r.json()["hourly"])
        w["time"] = pd.to_datetime(w["time"])
        w = w.set_index("time")
        w.index = w.index.tz_localize(TZ)
        _wx_recent, _wx_recent_at = w, _time.time()
    return _wx_recent

def get_weather_combined():
    """Archive weather extended with recent/today rows it doesn't cover."""
    hist = get_weather_df()
    try:
        rec = get_weather_recent()
        return pd.concat([hist, rec[rec.index > hist.index.max()]])
    except Exception:
        return hist

def pvlib_predict(idx):
    sp = pvlib.solarposition.get_solarposition(idx, LAT, LON)
    w = get_weather_combined()
    w_sel = w.reindex(idx, method="nearest", tolerance=pd.Timedelta("35min")).dropna(subset=["shortwave_radiation"])
    common = idx.intersection(w_sel.index)
    if len(common) == 0:
        return pd.Series(0.0, index=idx)
    poa = pvlib.irradiance.get_total_irradiance(
        TILT, AZIM,
        sp.loc[common,"apparent_zenith"], sp.loc[common,"azimuth"],
        dni=w_sel.loc[common,"direct_normal_irradiance"],
        ghi=w_sel.loc[common,"shortwave_radiation"],
        dhi=w_sel.loc[common,"diffuse_radiation"],
        dni_extra=pvlib.irradiance.get_extra_radiation(common), model="haydavies")
    tcell = pvlib.temperature.sapm_cell(
        poa.poa_global, w_sel.loc[common,"temperature_2m"], w_sel.loc[common,"wind_speed_10m"],
        **pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_polymer"])
    pred = pvlib.pvsystem.pvwatts_dc(poa.poa_global, tcell, PDC0, GAMMA).clip(lower=0)
    return pred.reindex(idx, fill_value=0.0)

# ════════════════════════════════════════════════════════════════════
#  LIVE
# ════════════════════════════════════════════════════════════════════
@app.get("/live")
def get_live():
    """Today's curve: parquet history (if it already covers today) merged
    with live LSW-3 readings. Falls back to the most recent day with data
    (e.g. before dawn, when the inverter is still off)."""
    df = get_full()
    day = date.today()
    df_day = df[df['t'].dt.date == day]
    if df_day.empty:
        day = df['t'].max().date()
        df_day = df[df['t'].dt.date == day]
    out = [{"ts": r.t.isoformat(), "ac_power": float(r.power_w or 0)}
           for r in df_day.itertuples()]
    seen, unique = set(), []
    for item in out:
        k = item['ts'][:16]
        if k not in seen: seen.add(k); unique.append(item)
    unique.sort(key=lambda x: x['ts'])
    return unique[-288:]

# ════════════════════════════════════════════════════════════════════
#  HISTORICAL DAY WITH PVLIB COMPARISON
# ════════════════════════════════════════════════════════════════════
@app.get("/production/{day}")
def get_production(day: str):
    try: target = pd.to_datetime(day).date()
    except: raise HTTPException(400, "Date must be YYYY-MM-DD")
    df = get_full()
    day_df = df[df['t'].dt.date == target].copy()
    if day_df.empty: raise HTTPException(404, f"No data for {day}")
    day_df = day_df.set_index('t').sort_index()
    day_df.index = day_df.index.tz_localize(TZ, ambiguous='infer', nonexistent='shift_forward')
    actual = day_df['power_w'].resample("5min").mean().fillna(0)
    pred   = pvlib_predict(actual.index)
    actual_kwh = round(actual.sum() * 5/60/1000, 2)
    pred_kwh   = round(pred.sum()   * 5/60/1000, 2)
    mape = round(abs(actual_kwh - pred_kwh) / max(actual_kwh, 0.1) * 100, 1)
    hourly = [{"time": ts.strftime("%H:%M"),
               "actual_w": round(float(act_w), 1),
               "predicted_w": round(float(pred.get(ts, 0.0)), 1)}
              for ts, act_w in actual.items()]
    return {"date": str(target), "actual_kwh": actual_kwh,
            "predicted_kwh": pred_kwh, "accuracy_pct": round(100-mape, 1), "hourly": hourly}

# ════════════════════════════════════════════════════════════════════
#  AVAILABLE DATES
# ════════════════════════════════════════════════════════════════════
@app.get("/available_dates")
def available_dates():
    df = get_full()
    dates = sorted(df['t'].dt.date.unique().tolist(), reverse=True)
    return [str(d) for d in dates]

# ════════════════════════════════════════════════════════════════════
#  YIELD
# ════════════════════════════════════════════════════════════════════
@app.get("/yield")
def get_yield():
    """Today's kWh. Prefers the inverter's own yield-today counter
    (register 60) from live readings; falls back to integrating power."""
    today = date.today()
    lv = live_readings(today)
    if len(lv) and lv["yield_today"].notna().any():
        return [{"date": str(today),
                 "yield": round(float(lv["yield_today"].max()), 1),
                 "source": "inverter_register_60"}]
    df = get_full()
    d = df[df['t'].dt.date == today]
    if d.empty:
        day = df['t'].max().date()
        d = df[df['t'].dt.date == day]
        today = day
    # 5-min watt samples -> kWh needs the 5/60 hour factor
    kwh = round(float(d['power_w'].sum()) * 5 / 60 / 1000, 2)
    return [{"date": str(today), "yield": kwh, "source": "integrated"}]

# ════════════════════════════════════════════════════════════════════
#  FORECAST
# ════════════════════════════════════════════════════════════════════
@app.get("/forecast")
def get_forecast():
    """Tomorrow's quantile forecast. Regenerates forecast.json when it is
    missing, for the wrong date, or older than 6 h."""
    tomorrow = str(date.today() + timedelta(days=1))
    doc = None
    try:
        with open("forecast.json") as f: doc = json.load(f)
        if (not isinstance(doc, dict) or doc.get("date") != tomorrow
                or (datetime.now() - datetime.fromisoformat(doc["generated_at"])
                    ).total_seconds() > 6 * 3600):
            doc = None
    except Exception:
        doc = None
    if doc is None:
        try:
            import export_forecast
            doc = export_forecast.generate()
        except Exception as e:
            return {"hourly": [], "summary": {}, "error": str(e)}
    data = doc["hourly"]
    return {"date": doc["date"], "generated_at": doc["generated_at"],
            "hourly": data, "summary": {
            "expected_kwh": round(sum(d['p50'] for d in data)/1000, 2),
            "worst_kwh":    round(sum(d['p10'] for d in data)/1000, 2),
            "best_kwh":     round(sum(d['p90'] for d in data)/1000, 2),
        }}

# ════════════════════════════════════════════════════════════════════
#  SAVINGS  (₹ saved vs grid)
# ════════════════════════════════════════════════════════════════════
@app.get("/savings")
def get_savings(consumption: int = 600):
    """Slab-based savings against the TNEB telescopic tariff (tneb.py).

    `consumption` = assumed gross household usage per bi-monthly billing
    cycle. There is no CT clamp, so this is an assumption the user sets
    (estimate it from a TNEB bill), not a measurement. Solar's value under
    telescopic slabs depends heavily on it: ~Rs 2.4/kWh at 400 units up to
    ~Rs 10/kWh at 1000 units.
    """
    df = get_full()
    df_s = df.copy()
    df_s['kwh'] = df_s['power_w'] * 5/60/1000   # each row = 5-min reading

    today = date.today()
    this_month_start = today.replace(day=1)
    this_year_start  = today.replace(month=1, day=1)

    today_kwh  = float(df_s[df_s['t'].dt.date == today]['kwh'].sum())
    month_kwh  = float(df_s[df_s['t'].dt.date >= this_month_start]['kwh'].sum())
    year_kwh   = float(df_s[df_s['t'].dt.date >= this_year_start]['kwh'].sum())
    total_kwh  = float(df_s['kwh'].sum())

    # bi-monthly TNEB cycles, approximated as calendar month pairs
    per = df_s['t'].dt.to_period('M')
    df_s['month'] = per
    df_s['cycle'] = [f"{p.year}-C{(p.month + 1) // 2}" for p in per]
    cyc = df_s.groupby('cycle')['kwh'].sum()
    cycles = [{"cycle": c, "solar_kwh": round(float(v), 1),
               "saved_rs": tneb.savings(consumption, float(v)),
               "eff_rate": tneb.effective_rate(consumption, float(v))}
              for c, v in cyc.items()]
    total_saved_rs = float(sum(c["saved_rs"] for c in cycles))
    year_saved_rs = float(sum(c["saved_rs"] for c in cycles
                              if c["cycle"].startswith(str(today.year))))

    # blended rate on a typical full cycle, for intra-cycle displays
    typical_cycle_kwh = float(cyc[:-1].mean()) if len(cyc) > 1 else float(cyc.mean())
    rate = tneb.effective_rate(consumption, typical_cycle_kwh)

    # monthly chart: cycle savings split across its months pro-rata by kWh
    monthly = df_s.groupby('month')['kwh'].sum().tail(12)
    saved_by_cycle = {c["cycle"]: c for c in cycles}
    monthly_chart = []
    for m, v in monthly.items():
        c = saved_by_cycle[f"{m.year}-C{(m.month + 1) // 2}"]
        share = float(v) / c["solar_kwh"] if c["solar_kwh"] else 0
        monthly_chart.append({"month": str(m), "kwh": round(float(v), 1),
                              "savings": round(c["saved_rs"] * share, 0)})

    remaining_rs = max(0.0, INSTALL_COST_RS - total_saved_rs)
    avg_monthly_rs = (sum(m["savings"] for m in monthly_chart)
                      / max(len(monthly_chart), 1))
    months_to_breakeven = round(remaining_rs / max(avg_monthly_rs, 1), 1) \
        if remaining_rs > 0 else 0.0
    pct_recovered = round(min(100.0, total_saved_rs / INSTALL_COST_RS * 100), 1)

    return {
        "tariff_rs_per_kwh": rate,          # effective, not flat
        "assumed_consumption": consumption,
        "tariff_note": ("TNEB telescopic slabs; assumed "
                        f"{consumption} units gross use per bi-monthly cycle "
                        "(no CT clamp - set this from your TNEB bill)"),
        "install_cost_rs": INSTALL_COST_RS,
        "today_kwh":  round(today_kwh, 2),  "today_rs":  round(today_kwh * rate, 2),
        "month_kwh":  round(month_kwh, 2),  "month_rs":  round(month_kwh * rate, 2),
        "year_kwh":   round(year_kwh, 2),   "year_rs":   round(year_saved_rs, 2),
        "total_kwh":  round(total_kwh, 2),  "total_rs":  round(total_saved_rs, 2),
        "pct_recovered": pct_recovered,
        "months_to_breakeven": months_to_breakeven,
        "breakeven_achieved": bool(remaining_rs == 0),
        "monthly_chart": monthly_chart,
        "cycles": cycles,
    }

# ════════════════════════════════════════════════════════════════════
#  ENVIRONMENTAL IMPACT
# ════════════════════════════════════════════════════════════════════
@app.get("/impact")
def get_impact():
    df = get_full()
    total_kwh = df['power_w'].sum() * 5/60/1000

    today = date.today()
    this_month_start = today.replace(day=1)
    this_year_start  = today.replace(month=1, day=1)
    today_kwh  = df[df['t'].dt.date == today]['power_w'].sum() * 5/60/1000
    month_kwh  = df[df['t'].dt.date >= this_month_start]['power_w'].sum() * 5/60/1000
    year_kwh   = df[df['t'].dt.date >= this_year_start]['power_w'].sum() * 5/60/1000

    total_co2_kg = total_kwh * CO2_KG_PER_KWH
    year_co2_kg  = year_kwh  * CO2_KG_PER_KWH
    month_co2_kg = month_kwh * CO2_KG_PER_KWH
    today_co2_kg = today_kwh * CO2_KG_PER_KWH

    # Operational years
    df_sorted = df.sort_values('t')
    op_years = max(0.1, (df_sorted['t'].max() - df_sorted['t'].min()).days / 365)

    # Tree equivalents — lifetime CO₂ / (22 kg/tree/year × op_years)
    trees_equivalent = round(total_co2_kg / (CO2_PER_TREE_PER_YR * op_years), 1)

    # Monthly CO₂ chart
    df_c = df.copy()
    df_c['kwh'] = df_c['power_w'] * 5/60/1000
    df_c['month'] = df_c['t'].dt.to_period('M')
    monthly = df_c.groupby('month')['kwh'].sum().tail(12)
    monthly_chart = [{"month": str(m), "co2_kg": round(v * CO2_KG_PER_KWH, 1)}
                     for m, v in monthly.items()]

    # Fun comparisons
    petrol_litres   = round(total_co2_kg / 2.31, 1)   # 1L petrol ≈ 2.31 kg CO₂
    phone_charges   = round(total_kwh / 0.012)          # avg phone = 12 Wh per charge
    led_bulb_hours  = round(total_kwh / 0.01)           # 10W bulb

    return {
        "total_kwh":     round(total_kwh,   1),
        "today_co2_kg":  round(today_co2_kg,  2),
        "month_co2_kg":  round(month_co2_kg,  1),
        "year_co2_kg":   round(year_co2_kg,   1),
        "total_co2_kg":  round(total_co2_kg,  1),
        "trees_equivalent": trees_equivalent,
        "op_years":      round(op_years, 1),
        "petrol_litres":  petrol_litres,
        "phone_charges":  phone_charges,
        "led_bulb_hours": led_bulb_hours,
        "monthly_chart":  monthly_chart,
    }

# ════════════════════════════════════════════════════════════════════
#  CLEANING RECOMMENDATION
# ════════════════════════════════════════════════════════════════════
@app.get("/cleaning")
def get_cleaning():
    try:
        daily = pd.read_csv("daily.csv", index_col=0, parse_dates=True)
        daily = daily.dropna(subset=['ratio'])

        recent_7   = daily.tail(7)['ratio'].mean()
        baseline   = daily.iloc[-31:-7]['ratio'].mean() if len(daily) >= 31 else daily['ratio'].quantile(0.75)

        soiling_pct = max(0.0, (baseline - recent_7) / baseline * 100)
        recent_avg_kwh = daily.tail(7)['kwh'].mean()
        daily_loss_kwh = recent_avg_kwh * soiling_pct / 100
        daily_loss_rs  = daily_loss_kwh * TARIFF_RS_PER_KWH

        # Trend over last 30 days
        trend = daily.tail(30)[['ratio']].copy().reset_index()
        trend_chart = [{"date": str(r['index'].date()), "ratio": round(r['ratio'], 3)}
                       for _, r in trend.iterrows()]

        if soiling_pct < 2:
            status = "clean"
            title  = "Panels are Clean ✅"
            detail = "Your panels are performing above their recent baseline. No cleaning needed right now."
            color  = "#10b981"
        elif soiling_pct < 6:
            status = "mild"
            title  = "Mild Soiling Detected 🟡"
            detail = f"Performance is ~{soiling_pct:.1f}% below baseline. Cleaning is optional — you're losing about ₹{daily_loss_rs:.0f}/day."
            color  = "#f59e0b"
        else:
            status = "dirty"
            title  = "Cleaning Recommended 🔴"
            detail = f"Performance is {soiling_pct:.1f}% below baseline. You're losing ₹{daily_loss_rs:.0f}/day — cleaning will pay for itself quickly."
            color  = "#ef4444"

        return {
            "status": status, "title": title, "detail": detail, "color": color,
            "soiling_pct": round(soiling_pct, 1),
            "daily_loss_kwh": round(daily_loss_kwh, 2),
            "daily_loss_rs":  round(daily_loss_rs, 0),
            "recent_ratio":   round(recent_7, 3),
            "baseline_ratio": round(baseline, 3),
            "trend_chart":    trend_chart,
        }
    except Exception as e:
        return {"error": str(e)}

# ════════════════════════════════════════════════════════════════════
#  WEATHER
# ════════════════════════════════════════════════════════════════════
@app.get("/weather")
def get_weather():
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation_probability,precipitation,"
                      "cloud_cover,shortwave_radiation,wind_speed_10m,weathercode",
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,"
                     "precipitation_sum,sunshine_duration,uv_index_max",
            "timezone": "Asia/Kolkata",
            "start_date": tomorrow, "end_date": tomorrow,
        }, timeout=10)
        r.raise_for_status(); raw = r.json()
        hourly, daily_r = raw["hourly"], raw["daily"]
        hourly_out = []
        for i, t in enumerate(hourly["time"]):
            h = int(t[11:13])
            if 5 <= h <= 20:
                wc = hourly["weathercode"][i]
                hourly_out.append({"time": t[11:16], "temp": hourly["temperature_2m"][i],
                    "rain_chance": hourly["precipitation_probability"][i],
                    "rain_mm": hourly["precipitation"][i], "cloud": hourly["cloud_cover"][i],
                    "solar_rad": hourly["shortwave_radiation"][i],
                    "wind_kmh": hourly["wind_speed_10m"][i],
                    "icon": _wicon(wc), "label": _wlabel(wc)})
        daily_out = {
            "temp_max": daily_r["temperature_2m_max"][0], "temp_min": daily_r["temperature_2m_min"][0],
            "rain_mm": daily_r["precipitation_sum"][0],
            "sunshine_hrs": round(daily_r["sunshine_duration"][0]/3600, 1),
            "uv_index": daily_r["uv_index_max"][0],
            "icon": _wicon(daily_r["weathercode"][0]), "label": _wlabel(daily_r["weathercode"][0]),
        }
        cloud_avg = sum(hourly["cloud_cover"][i] for i, t in enumerate(hourly["time"])
                        if 6 <= int(t[11:13]) <= 18) / 13
        rain_total = sum(hourly["precipitation"])
        if cloud_avg < 20 and rain_total < 1:
            impact = {"level":"great","color":"#10b981","text":"Excellent day for solar! Clear skies expected. Panels will run near peak."}
        elif cloud_avg < 45:
            impact = {"level":"good","color":"#f59e0b","text":"Mostly sunny with some clouds — around 80–90% of your best days."}
        elif cloud_avg < 70:
            impact = {"level":"moderate","color":"#f97316","text":"Partly cloudy. Expect roughly 50–70% of a clear day."}
        else:
            impact = {"level":"poor","color":"#ef4444","text":"Heavy cloud or rain likely. Production may fall to 20–40% of normal."}
        return {"hourly": hourly_out, "daily": daily_out, "impact": impact}
    except Exception as e: return {"error": str(e)}

def _wicon(c):
    if c==0: return "☀️"
    if c in [1,2]: return "🌤️"
    if c==3: return "☁️"
    if c in [45,48]: return "🌫️"
    if c in [51,53,55,61,63]: return "🌦️"
    if c in [65,80,81,82]: return "🌧️"
    if c in [71,73,75,77]: return "❄️"
    if c in [95,96,99]: return "⛈️"
    return "🌤️"

def _wlabel(c):
    if c==0: return "Clear"
    if c in [1,2]: return "Partly Cloudy"
    if c==3: return "Overcast"
    if c in [45,48]: return "Foggy"
    if c in [51,53,55]: return "Drizzle"
    if c in [61,63,65]: return "Rain"
    if c in [80,81,82]: return "Showers"
    if c in [95,96,99]: return "Thunderstorm"
    return "Partly Cloudy"

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
