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

import consumption as consumption_meter
import tneb

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

LAT, LON, TZ = 10.79, 78.70, "Asia/Kolkata"
TILT, AZIM   = 10.0, 105.0
PDC0, GAMMA  = 2674, -0.0035

# ── Config (can be user-adjusted later) ──────────────────────────────
TARIFF_RS_PER_KWH    = 7.0      # Effective rate saved per kWh (TANGEDCO offset)
INSTALL_COST_RS      = 150000   # Actual install cost ₹1,50,000 for 3 kWp
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
    to yesterday; today comes from here.

    Register 109 ("AC power") is untrustworthy in low sun - observed stuck
    near 2 kW while the energy counter and phase currents showed <200 W
    (2026-07-10 afternoon). Each reading is sanity-checked against the
    power implied by the yield-counter slope; failures are replaced by
    that estimate and flagged in `estimated`."""
    day = day or date.today()
    try:
        con = sqlite3.connect("solar.db")
        df = pd.read_sql(
            "SELECT ts, ac_power, yield_today FROM readings WHERE ts LIKE ?",
            con, params=(f"{day}%",))
        con.close()
    except Exception:
        return pd.DataFrame(columns=["t", "power_w", "yield_today", "estimated"])
    df["t"] = pd.to_datetime(df["ts"])
    df["power_w"] = df["ac_power"].astype(float)
    df = df.sort_values("t").reset_index(drop=True)
    # W implied by the yield counter (0.1 kWh steps -> smooth over ~30 min)
    hrs = df["t"].diff().dt.total_seconds() / 3600
    inst = (df["yield_today"].diff() * 1000 / hrs).where(hrs > 0)
    slope_w = inst.rolling(6, min_periods=2).mean()
    bad = (df["power_w"] > 600) & slope_w.notna() \
        & (df["power_w"] > 4 * slope_w.clip(lower=50))
    df["estimated"] = bad
    df.loc[bad, "power_w"] = slope_w[bad].clip(lower=0)
    return df[["t", "power_w", "yield_today", "estimated"]]

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

def _tneb_cycles():
    """Measured reality from the TNEB net-metering bills (tneb_bills.csv):
    per billing cycle, the meter's import/export + our measured generation
    give actual household consumption and actual savings - no CT clamp
    needed for history. gross = import + (generation - export);
    saved = bill(gross, telescopic) - CC actually charged. Fixed charges
    and wiped March export credits are not counted (conservative).
    Historical cycles are priced at the CURRENT (May-2026) tariff - the
    pre-May rate table is not on file."""
    try:
        bills = pd.read_csv("tneb_bills.csv", parse_dates=["start_date", "end_date"])
    except FileNotFoundError:
        return []
    df = get_hist()
    span0 = df["t"].min()
    out = []
    for _, b in bills.iterrows():
        m = (df["t"] >= b.start_date) & (df["t"] < b.end_date + pd.Timedelta(days=1))
        gen = float(df.loc[m, "power_w"].sum() * 5 / 60 / 1000)
        win_days = max(1, (b.end_date - b.start_date).days)
        ov0 = max(b.start_date, span0)
        overlap = max(0, (b.end_date - ov0).days)
        estimated = overlap < win_days
        if overlap >= 0.9 * win_days and overlap < win_days:
            gen = gen * win_days / overlap          # scale a small gap
        row = {"from": str(b.start_date.date()), "to": str(b.end_date.date()),
               "start": b.start_date, "end": b.end_date,
               "import_units": round(float(b.import_units), 1),
               "export_units": round(float(b.export_units), 1),
               "billed_units": round(float(b.billed_units), 1),
               "cc_paid_rs": float(b.cc_charges),
               "estimated": bool(estimated),
               "generation_kwh": round(gen, 1) if overlap >= 0.9 * win_days else None}
        if row["generation_kwh"] and gen > 0:
            self_used = max(0.0, gen - float(b.export_units))
            gross = float(b.import_units) + self_used
            # a window longer than one bi-monthly cycle (meter-reading skip)
            # must be priced as multiple cycles - telescopic slabs reset
            n_cyc = max(1, round(win_days / 61))
            no_solar_bill = tneb.bill(gross / n_cyc) * n_cyc
            saved = round(no_solar_bill - float(b.cc_charges), 0)
            row.update({"self_consumed_kwh": round(self_used, 1),
                        "gross_consumption": round(gross, 1),
                        "bill_without_solar_rs": round(no_solar_bill, 0),
                        "saved_rs": saved,
                        "realized_rate": round(saved / gen, 2)})
        out.append(row)
    return out


@app.get("/tneb")
def get_tneb():
    cycles = _tneb_cycles()
    out = [{k: v for k, v in c.items() if k not in ("start", "end")}
           for c in cycles]
    tot_saved = sum(c.get("saved_rs", 0) for c in cycles)
    measured = [c for c in out if "saved_rs" in c]
    avg_gross = (sum(c["gross_consumption"] for c in measured) / len(measured)
                 if measured else None)
    return {"cycles": out,
            "measured_cycles": len(measured),
            "total_saved_rs": round(tot_saved, 0),
            "avg_gross_units_per_cycle": round(avg_gross, 0) if avg_gross else None,
            "avg_self_consumption_pct": round(
                100 * sum(c["self_consumed_kwh"] for c in measured)
                / max(1e-9, sum(c["generation_kwh"] for c in measured)), 1)
                if measured else None,
            "note": ("savings = telescopic bill on measured gross consumption "
                     "minus CC actually paid; fixed charges + wiped export "
                     "credits excluded (conservative)")}


@app.post("/consumption/reading")
def post_consumption(body: dict):
    """Ingestion contract for a future CT clamp / energy meter (see
    consumption.py). No meter exists today; when one starts posting here,
    /savings switches from assumed to measured usage automatically."""
    if "load_w" not in body:
        raise HTTPException(400, "load_w (watts) is required")
    ts = consumption_meter.add_reading(
        float(body["load_w"]),
        import_w=body.get("import_w"), export_w=body.get("export_w"),
        source=str(body.get("source", "meter")), ts=body.get("ts"))
    return {"stored": ts}


@app.get("/consumption/status")
def consumption_status():
    return {"meter_present": consumption_meter.has_data(),
            "latest": consumption_meter.latest(),
            "note": "no CT clamp installed - POST /consumption/reading "
                    "from any meter to activate measured-usage analytics"}


@app.get("/now")
def get_now():
    """Instantaneous state for the live flow animation: latest inverter
    reading (DC in, AC out) + this hour's weather. The house/grid split is
    NOT known (no CT clamp) - the UI shows flow on those paths but no
    numbers."""
    out = {"ts": None, "ac_w": 0.0, "estimated": False, "fresh": False,
           "cloud": 0, "rain_mm": 0.0, "wind_kmh": 0.0, "sun_wm2": 0.0}
    try:
        lv = live_readings()   # sanity-gated: reg 109 lies in low sun
        if len(lv):
            r = lv.iloc[-1]
            out["ts"] = r["t"].isoformat()
            out["ac_w"] = float(r["power_w"])
            out["estimated"] = bool(r["estimated"])
            age = (datetime.now() - r["t"]).total_seconds()
            out["fresh"] = bool(age < 1800)
    except Exception:
        pass
    try:
        w = get_weather_recent()
        now = pd.Timestamp.now(tz=TZ).floor("h")
        if now in w.index:
            row = w.loc[now]
            out["cloud"] = int(row.cloud_cover)
            out["rain_mm"] = float(row.precipitation)
            out["wind_kmh"] = float(row.wind_speed_10m)
            out["sun_wm2"] = float(row.shortwave_radiation)
    except Exception:
        pass
    return out

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
    """7-day quantile forecast. Regenerates forecast.json when it is
    missing, doesn't start today, or is older than 4 h (weather models
    refresh every few hours - don't predict off stale weather)."""
    today = str(date.today())
    doc = None
    try:
        with open("forecast.json") as f: doc = json.load(f)
        if (not isinstance(doc, dict) or "days" not in doc
                or not doc["days"] or doc["days"][0]["date"] != today
                or (datetime.now() - datetime.fromisoformat(doc["generated_at"])
                    ).total_seconds() > 4 * 3600):
            doc = None
    except Exception:
        doc = None
    if doc is None:
        try:
            import export_forecast
            doc = export_forecast.generate()
        except Exception as e:
            return {"days": [], "error": str(e)}
    return doc

# ════════════════════════════════════════════════════════════════════
#  SAVINGS  (₹ saved vs grid)
# ════════════════════════════════════════════════════════════════════
@app.get("/savings")
def get_savings():
    """MEASURED savings, anchored on the real TNEB net-metering bills
    (_tneb_cycles): billed cycles use actual import/export + generation;
    the current unbilled cycle and intra-day/month displays are valued at
    the trailing realized Rs/kWh (last 3 billed cycles). Falls back to a
    600-unit assumption only if tneb_bills.csv is absent."""
    df = get_full()
    df_s = df.copy()
    df_s['kwh'] = df_s['power_w'] * 5/60/1000   # each row = 5-min reading

    today = date.today()
    this_month_start = today.replace(day=1)
    this_year_start = today.replace(month=1, day=1)
    today_kwh = float(df_s[df_s['t'].dt.date == today]['kwh'].sum())
    month_kwh = float(df_s[df_s['t'].dt.date >= this_month_start]['kwh'].sum())
    year_kwh = float(df_s[df_s['t'].dt.date >= this_year_start]['kwh'].sum())
    total_kwh = float(df_s['kwh'].sum())

    cycles = _tneb_cycles()
    measured = [c for c in cycles if c.get("saved_rs") is not None]
    if not measured:
        # no bills on file - old assumption-based estimate at 600 units
        rate = tneb.effective_rate(600, 800)
        est = total_kwh * rate
        return {"tariff_rs_per_kwh": rate, "usage_source": "assumed",
                "install_cost_rs": INSTALL_COST_RS,
                "today_kwh": round(today_kwh, 2), "today_rs": round(today_kwh * rate, 2),
                "month_kwh": round(month_kwh, 2), "month_rs": round(month_kwh * rate, 2),
                "year_kwh": round(year_kwh, 2), "year_rs": round(year_kwh * rate, 2),
                "total_kwh": round(total_kwh, 2), "total_rs": round(est, 2),
                "pct_recovered": round(min(100, est / INSTALL_COST_RS * 100), 1),
                "months_to_breakeven": None, "breakeven_achieved": False,
                "monthly_chart": [], "tariff_note": "no TNEB bills on file"}

    measured_saved = float(sum(c["saved_rs"] for c in measured))
    measured_gen = float(sum(c["generation_kwh"] for c in measured))
    realized_rate = measured_saved / max(measured_gen, 1e-9)
    trailing = measured[-3:]
    trailing_rate = (sum(c["saved_rs"] for c in trailing)
                     / max(1e-9, sum(c["generation_kwh"] for c in trailing)))

    # current unbilled cycle: production since the last meter reading,
    # valued at the trailing realized rate (estimate until the next bill)
    last_end = max(c["end"] for c in cycles)
    cur_kwh = float(df_s.loc[df_s['t'] >= last_end, 'kwh'].sum())
    cur_est_rs = cur_kwh * trailing_rate
    total_saved_rs = measured_saved + cur_est_rs

    year_saved_rs = float(sum(
        c["saved_rs"] for c in measured
        if pd.Timestamp(c["end"]).year == today.year)) + cur_est_rs

    # monthly chart: each month's kWh valued at its billing cycle's
    # realized rate; months after the last bill use the trailing rate
    df_s['month'] = df_s['t'].dt.to_period('M')
    monthly = df_s.groupby('month')['kwh'].sum().tail(12)
    def _rate_for(mstart):
        mid = mstart + pd.Timedelta(days=15)
        for c in measured:
            if c["start"] <= mid <= c["end"]:
                return c["realized_rate"]
        return trailing_rate
    monthly_chart = [{"month": str(m), "kwh": round(float(v), 1),
                      "savings": round(float(v) * _rate_for(m.to_timestamp()), 0)}
                     for m, v in monthly.items()]

    # breakeven from the measured run-rate (Rs per month since first bill)
    first_start = min(c["start"] for c in measured)
    months_elapsed = max(1.0, (pd.Timestamp(today) - first_start).days / 30.44)
    run_rate = total_saved_rs / months_elapsed
    remaining_rs = max(0.0, INSTALL_COST_RS - total_saved_rs)
    months_to_breakeven = round(remaining_rs / max(run_rate, 1), 1) \
        if remaining_rs > 0 else 0.0
    pct_recovered = round(min(100.0, total_saved_rs / INSTALL_COST_RS * 100), 1)

    avg_gross = sum(c["gross_consumption"] for c in measured) / len(measured)
    return {
        "tariff_rs_per_kwh": round(realized_rate, 2),   # realized, measured
        "trailing_rate": round(trailing_rate, 2),
        "usage_source": "measured",
        "avg_gross_units": round(avg_gross, 0),
        "tariff_note": ("realized Rs/kWh from real TNEB bills (import/export "
                        "meter + measured generation); current cycle estimated "
                        "at trailing rate; history priced at the May-2026 "
                        "tariff - pre-May rate table not on file"),
        "install_cost_rs": INSTALL_COST_RS,
        "today_kwh":  round(today_kwh, 2),  "today_rs":  round(today_kwh * trailing_rate, 2),
        "month_kwh":  round(month_kwh, 2),  "month_rs":  round(month_kwh * trailing_rate, 2),
        "year_kwh":   round(year_kwh, 2),   "year_rs":   round(year_saved_rs, 2),
        "total_kwh":  round(total_kwh, 2),  "total_rs":  round(total_saved_rs, 2),
        "current_cycle_since": str(pd.Timestamp(last_end).date()),
        "current_cycle_est_rs": round(cur_est_rs, 0),
        "pct_recovered": pct_recovered,
        "months_to_breakeven": months_to_breakeven,
        "breakeven_achieved": bool(remaining_rs == 0),
        "monthly_chart": monthly_chart,
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

    # Tree equivalents - lifetime CO₂ / (22 kg/tree/year × op_years)
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
    """Soiling assessment with honest uncertainty.

    Compares the last 10 days' performance ratio (actual vs *weather-
    corrected* physics expectation, pr_daily.csv) against the prior
    30 days, with a bootstrap CI and Mann-Whitney p-value. There is no
    soiling sensor and the deposition hypothesis failed controlled
    testing, so this can only ever say "possible"/"likely" - never a
    confident 0% or a cleaning promise.
    """
    try:
        from scipy.stats import mannwhitneyu

        pr = pd.read_csv("pr_daily.csv", index_col=0, parse_dates=True)
        pr = pr.dropna(subset=["PR"])
        pr = pr[pr.PR.between(0.2, 1.6)]
        recent = pr.PR.tail(10).to_numpy()
        base = pr.PR.iloc[-40:-10].to_numpy()
        if len(recent) < 5 or len(base) < 15:
            return {"error": "not enough usable days for a verdict"}

        delta = (np.median(recent) / np.median(base) - 1) * 100
        rng = np.random.default_rng(0)
        boots = np.array([
            np.median(rng.choice(recent, recent.size)) /
            np.median(rng.choice(base, base.size)) - 1
            for _ in range(2000)]) * 100
        lo, hi = np.percentile(boots, [2.5, 97.5])
        p = float(mannwhitneyu(recent, base, alternative="less").pvalue)

        # washing-rain context (>5 mm/day resets deposition)
        w = get_weather_combined()
        rain = w.precipitation.resample("D").sum()
        washed = rain[rain > 5]
        days_since_rain = int((rain.index[-1] - washed.index[-1]).days) if len(washed) else None
        noise_pct = round(p * 100)
        rain_note = (f" It rained {days_since_rain} day(s) ago, which usually washes "
                     "the panels - so a dip right now is probably not dirt."
                     if days_since_rain is not None and days_since_rain <= 3 else "")

        if delta <= -5 and p < 0.05:
            recent_kwh = float(pr.act.tail(10).mean() / 1000)
            loss_lo = max(0.0, -hi) / 100 * recent_kwh   # conservative end
            loss_hi = -lo / 100 * recent_kwh
            status, color = "likely", "#ef4444"
            title = "Panels Likely Need Cleaning"
            detail = (f"Output has been about {-delta:.0f}% below usual for days, and "
                      f"that's too steady to be weather. You're losing roughly "
                      f"{loss_lo:.1f}-{loss_hi:.1f} units a day - a wash should help. "
                      f"(Judged from output; we can't see the glass itself.){rain_note}")
        elif delta <= -2 and p < 0.25:
            status, color = "possible", "#f59e0b"
            title = "Possible Light Dirt"
            detail = (f"Output is about {-delta:.0f}% below usual. It might be dirt, but "
                      f"there's a {noise_pct}% chance it's just weather noise. Wait for a "
                      f"few sunny days before deciding to clean.{rain_note}")
        else:
            status, color = "no_evidence", "#10b981"
            title = "Surface Probably Clean"
            detail = (f"The panels are producing about what they should for this "
                      f"weather ({delta:+.1f}% vs usual - within normal ups and downs). "
                      f"No sign of dirt build-up. Judged from output, not by looking "
                      f"at the glass.{rain_note}")

        trend = pr.PR.tail(30)
        trend_chart = [{"date": str(d.date()), "ratio": round(float(v), 3)}
                       for d, v in trend.items()]
        return {
            "status": status, "title": title, "detail": detail, "color": color,
            "delta_pct": round(float(delta), 1),
            "ci_low": round(float(lo), 1), "ci_high": round(float(hi), 1),
            "p_value": round(p, 3), "noise_pct": noise_pct,
            "days_since_rain": days_since_rain,
            "n_recent": int(recent.size), "n_baseline": int(base.size),
            "as_of": str(pr.index[-1].date()),
            "trend_chart": trend_chart,
        }
    except Exception as e:
        return {"error": str(e)}

# ════════════════════════════════════════════════════════════════════
#  WEATHER
# ════════════════════════════════════════════════════════════════════
@app.get("/weather")
def get_weather(day: str = ""):
    """Weather detail for one forecast day (default: tomorrow)."""
    try:
        target = pd.to_datetime(day).date().isoformat() if day else \
            (date.today() + timedelta(days=1)).isoformat()
    except Exception:
        target = (date.today() + timedelta(days=1)).isoformat()
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": LAT, "longitude": LON,
            "hourly": "temperature_2m,precipitation_probability,precipitation,"
                      "cloud_cover,shortwave_radiation,wind_speed_10m,weathercode",
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,"
                     "precipitation_sum,sunshine_duration,uv_index_max",
            "timezone": "Asia/Kolkata",
            "start_date": target, "end_date": target,
        }, timeout=10)
        r.raise_for_status(); raw = r.json()
        hourly, daily_r = raw["hourly"], raw["daily"]
        hourly_out = []
        # full 24 h - the forecast scene slider needs night hours too
        for i, t in enumerate(hourly["time"]):
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
            impact = {"level":"good","color":"#f59e0b","text":"Mostly sunny with some clouds - around 80–90% of your best days."}
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
