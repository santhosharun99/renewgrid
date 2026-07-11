"""Consumption integration point (CT clamp / energy meter - not yet installed).

This plant has no consumption metering today, and nothing in the project
fakes it. This module defines the CONTRACT so a meter can be added at any
time with zero refactoring:

Hardware options (any one):
  - Shelly EM / PZEM-004T + ESP32 on the house feed (~Rs 1,500-2,500)
  - a smart meter with a local/HTTP interface
  - TNEB smart meter data, if/when the utility exposes it

Whatever the device, it just POSTs to the API every few minutes:
    POST /consumption/reading  {"load_w": 843, "import_w": 620, "export_w": 0}
or writes rows here directly. The moment rows exist:
  - /savings switches from ASSUMED bi-monthly usage to MEASURED usage for
    every billing cycle with >=80% daily coverage (real slab position,
    real telescopic-tariff savings)
  - /now reports live house load alongside solar
  - self-consumption vs export split becomes computable

Schema: one row per reading; import/export optional (a single CT on the
mains gives net flow; separate CTs give both directions).
"""
import sqlite3
from datetime import datetime

DB = "solar.db"


def _con():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS consumption (
        ts TEXT PRIMARY KEY, load_w REAL, import_w REAL, export_w REAL,
        source TEXT)""")
    return con


def add_reading(load_w, import_w=None, export_w=None, source="meter", ts=None):
    ts = ts or datetime.now().isoformat(timespec="seconds")
    con = _con()
    con.execute("INSERT OR REPLACE INTO consumption VALUES (?,?,?,?,?)",
                (ts, load_w, import_w, export_w, source))
    con.commit()
    con.close()
    return ts


def has_data():
    con = _con()
    n = con.execute("SELECT count(*) FROM consumption").fetchone()[0]
    con.close()
    return n > 0


def latest():
    con = _con()
    r = con.execute("SELECT ts, load_w, import_w, export_w FROM consumption "
                    "ORDER BY ts DESC LIMIT 1").fetchone()
    con.close()
    return dict(ts=r[0], load_w=r[1], import_w=r[2], export_w=r[3]) if r else None


def daily_kwh():
    """Per-day consumed kWh from readings (assumes ~regular sampling;
    integrates load_w over actual intervals). Empty dict when no meter."""
    con = _con()
    rows = con.execute("SELECT ts, load_w FROM consumption ORDER BY ts").fetchall()
    con.close()
    out = {}
    prev = None
    for ts, w in rows:
        t = datetime.fromisoformat(ts)
        if prev is not None and w is not None:
            dt_h = min((t - prev[0]).total_seconds() / 3600, 0.5)  # cap gaps
            out[t.date()] = out.get(t.date(), 0.0) + (prev[1] or 0) * dt_h / 1000
        prev = (t, w)
    return out
