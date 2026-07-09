"""Daily Performance Ratio + degradation trend.

Uses the calibrated physics layer (physics.py / params.json) for expected
power and the shared quality gates — the old local tilt/azimuth fit and the
PR>0.5 outage heuristic are gone (events.csv is the outage authority).
"""
import numpy as np
import pandas as pd

import physics
import quality

df = quality.load_production()
ph = df.set_index("t")["power_w"].resample("h").mean()
ph.index = ph.index.tz_localize(physics.TZ)

w = physics.load_weather()
j = pd.DataFrame({"p": ph}).join(w, how="inner").dropna()
exp = physics.expected(j)
j["pred"], j["poa"] = exp["ac"], exp["poa"]

d = j[j.poa > 20].resample("D").agg(act=("p", "sum"), exp=("pred", "sum"),
                                    poa=("poa", "sum"))
d = d[d.poa > 2000]
d["PR"] = d.act / d.exp

d = quality.keep_days(d, quality.usable_days(df))
d = quality.exclude_events(d)

print("=== monthly Performance Ratio ===")
m = d.PR.resample("ME").mean()
print(m.round(3).to_string())

print("\n=== year-over-year, matched months ===")
for mo in range(1, 13):
    a = m[(m.index.month == mo) & (m.index <= m.index[0] + pd.Timedelta(days=365))]
    b = m[(m.index.month == mo) & (m.index > m.index[0] + pd.Timedelta(days=365))]
    if len(a) and len(b):
        print(f"  month {mo:2d}: {a.iloc[0]:.3f} -> {b.iloc[-1]:.3f}   "
              f"{(b.iloc[-1]/a.iloc[0]-1)*100:+.1f}%")

x = (d.index - d.index[0]).days.values
sl = np.polyfit(x, d.PR.values, 1)[0]
print(f"\nPR trend: {sl*365*100:+.2f} %-points per year")
print(f"relative: {sl*365/d.PR.mean()*100:+.2f} % per year")
print("(degradation claims need clear.py's bootstrap CI, not this raw trend)")

d.to_csv("pr_daily.csv")
print("\nsaved pr_daily.csv")
