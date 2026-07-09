"""One classifier for outage / fault / logger-gap / underperformance days.

Replaces the two disagreeing detectors (analyse.py eff-ratio, model.py a/e<0.5).

Classes and signatures:
  logger_gap        sample count < 130 (expected ~150/day), no zero-run evidence
  grid_outage       sustained zero power in high sun AND phase voltage ~ 0
  inverter_fault    sustained zero power in high sun AND phase voltage present
  outage_or_fault   sustained zero power in high sun, no voltage data available
                    (the whole 646-day app-export backfill: the export has no
                    phase voltage, so the outage-vs-fault split is UNAVAILABLE
                    there — this class says so instead of guessing)
  underperformance  power > 0 all day but actual/expected < 0.6 on a day with
                    non-trivial expected energy
  normal            otherwise

Voltage-based splitting only works on data collected by logger.py (solar.db
readings, regs 73-75), i.e. from 2026-07-09 onward.

Empirical note: during the confirmed 2024-09-20 EB outage the Solarman app
export *backfilled zeros* (147 samples, ~5 h of exact 0 W in high sun), while
the 2026-03-12 logger gap shows *missing rows* (53 samples, no zeros). A
sustained zero-run is therefore checked before the sample-count gate.

Run:  python outage_classifier.py         # classify all days, write events.csv
      python outage_classifier.py test    # unit tests (2024-09-20, 2026-03-12)
"""
import sqlite3
import sys
import numpy as np
import pandas as pd

import physics
import quality

ZERO_RUN_MIN = 60          # sustained zero power for >= this many minutes...
HIGH_SUN_W = 1000          # ...while physics expects at least this much AC.
# Both deliberately strict: dawn/dusk zeros under monsoon cloud and the
# ~07:30 eastern-house shading window produce short zero-runs at a few
# hundred expected watts on perfectly normal days.
UNDERPERF_RATIO = 0.6
MIN_EXPECTED_KWH = 5.0     # don't call underperformance on trivial days
TARIFF = 6.0               # Rs/kWh, indicative (TNEB slabs are telescopic)


def _zero_run_minutes(day, exp_by_hour):
    """Longest consecutive run of 0 W samples while expected AC >= HIGH_SUN_W."""
    hi = day.t.dt.floor("h").map(exp_by_hour).fillna(0) >= HIGH_SUN_W
    z = ((day.power_w == 0) & hi).to_numpy()
    best = run = 0
    for v in z:
        run = run + 1 if v else 0
        best = max(best, run)
    return best * 5


def _voltage_during(db, t0, t1):
    """Mean phase voltage from live logger readings inside [t0, t1]; None if
    no rows (historical data)."""
    try:
        con = sqlite3.connect(db)
        rows = con.execute(
            "SELECT v1,v2,v3 FROM readings WHERE ts >= ? AND ts <= ?",
            (t0.isoformat(), t1.isoformat())).fetchall()
        con.close()
    except sqlite3.Error:
        return None
    vals = [v for r in rows for v in r if v is not None]
    return float(np.mean(vals)) if vals else None


def classify_all(df=None, db="solar.db"):
    """-> DataFrame indexed by date: class, n, actual_kwh, expected_kwh,
    ratio, zero_run_min, lost_kwh, lost_rs."""
    if df is None:
        df = quality.load_production()
    w = physics.load_weather()
    exp = physics.expected(w)["ac"]
    exp_naive = exp.tz_localize(None)
    exp_daily = exp_naive.resample("D").sum() / 1000

    ph = df.set_index("t").power_w.resample("h").mean()
    act_daily = ph.resample("D").sum() / 1000

    out = []
    for date, day in df.groupby(df.t.dt.date):
        d = pd.Timestamp(date)
        e = float(exp_daily.get(d, np.nan))
        a = float(act_daily.get(d, np.nan))
        ratio = a / e if e and e > 0 else np.nan
        zrun = _zero_run_minutes(day, exp_naive)
        n = len(day)

        if zrun >= ZERO_RUN_MIN:
            zs = day[(day.power_w == 0)]
            v = _voltage_during(db, zs.t.min(), zs.t.max())
            if v is None:
                cls = "outage_or_fault"
            elif v < 50:
                cls = "grid_outage"
            else:
                cls = "inverter_fault"
        elif n < quality.MIN_SAMPLES:
            cls = "logger_gap"
        elif e >= MIN_EXPECTED_KWH and ratio < UNDERPERF_RATIO:
            cls = "underperformance"
        else:
            cls = "normal"

        # logger_gap days lost *data*, not production — no kWh/Rs charge
        lost = (max(e - a, 0.0)
                if cls not in ("normal", "logger_gap") and e > 0 else 0.0)
        out.append(dict(date=date, **{"class": cls}, n=n,
                        actual_kwh=round(a, 2), expected_kwh=round(e, 2),
                        ratio=round(ratio, 3) if e > 0 else np.nan,
                        zero_run_min=zrun,
                        lost_kwh=round(lost, 2),
                        lost_rs=round(lost * TARIFF, 0)))
    return pd.DataFrame(out).set_index("date")


def test():
    r = classify_all()
    c1 = r.loc[pd.Timestamp("2024-09-20").date(), "class"]
    c2 = r.loc[pd.Timestamp("2026-03-12").date(), "class"]
    ok1 = c1 == "outage_or_fault"   # known EB outage; voltage unavailable in
    ok2 = c2 == "logger_gap"        # backfill so outage/fault split is honest
    print(f"2024-09-20 -> {c1}  {'PASS' if ok1 else 'FAIL (want outage_or_fault)'}")
    print(f"2026-03-12 -> {c2}  {'PASS' if ok2 else 'FAIL (want logger_gap)'}")
    if not (ok1 and ok2):
        sys.exit(1)
    print("both tests pass")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test()
        sys.exit(0)
    r = classify_all()
    ev = r[r["class"] != "normal"]
    print(f"{len(r)} days classified; {len(ev)} events\n")
    print(ev.to_string())
    print("\nclass counts:")
    print(r["class"].value_counts().to_string())
    print(f"\ntotal lost: {ev.lost_kwh.sum():.1f} kWh  ~Rs {ev.lost_rs.sum():.0f}"
          f"  (at Rs {TARIFF}/kWh, indicative only — TNEB slabs are telescopic)")
    ev.to_csv("events.csv")
    print("saved events.csv")
