"""Task 7: calibrate the physics layer so the residual model stops paying
for a crude pvlib setup.

Fits tilt, azimuth, pdc0 and an eastern-shading horizon per cell-temperature
model (sapm / faiman / pvsyst), with a pvwatts inverter stage, on clear days
before 2026 (sun hours only). Reports clear-day R^2 before/after, in-sample
and on the 2026 holdout, on the same definition as the 0.903 headline
(top-5% VI days, GHI>300 hours). Winner is written to params.json, which
physics.expected() picks up everywhere.

Azimuth is weakly identified at 10 deg tilt (it hit the 90 deg bound in an
earlier fit) — bounds [60, 150] and don't over-interpret the fitted value.
"""
import json
import numpy as np
import pandas as pd
import pvlib
from scipy.optimize import minimize

import physics
import quality

df = quality.load_production()
ph = df.set_index("t")["power_w"].resample("h").mean()
ph.index = ph.index.tz_localize(physics.TZ)
w = physics.load_weather()
j = pd.DataFrame({"p": ph}).join(w, how="inner").dropna()

usable = quality.usable_days(df)
events = quality.event_days()
days = pd.read_csv("days.csv", parse_dates=["date"]).set_index("date")

clear40 = quality.clear_days(days) & (usable - events)
clear05 = {d.date() for d in days.index[days.vi <= days.vi.quantile(0.05)]} \
    & (usable - events)

j = quality.keep_days(j, clear40)
SP = pvlib.solarposition.get_solarposition(j.index, physics.LAT, physics.LON)
sun = j.shortwave_radiation > 300
fit_rows = sun & (j.index < pd.Timestamp("2026-01-01", tz=physics.TZ))
hold_rows = sun & ~fit_rows
in05 = pd.Series([ts.date() in clear05 for ts in j.index], index=j.index)

print(f"clear40 days {len(clear40)}  clear05 days {len(clear05)}  "
      f"fit hours {int(fit_rows.sum())}  2026-holdout hours {int(hold_rows.sum())}")


def r2(a, b):
    return float(np.corrcoef(a, b)[0, 1] ** 2)


def predict(p):
    return physics.expected(j, p, sp=SP)["ac"]


def report(name, p):
    ac = predict(p)
    daily_a = j.p[sun].resample("D").sum().dropna()
    daily_e = ac[sun].resample("D").sum().reindex(daily_a.index)
    mape = float((abs(daily_a - daily_e) / daily_a).mean() * 100)
    print(f"{name:34s} R2 fit {r2(ac[fit_rows], j.p[fit_rows]):.4f}  "
          f"holdout26 {r2(ac[hold_rows], j.p[hold_rows]):.4f}  "
          f"top5%VI {r2(ac[sun & in05], j.p[sun & in05]):.4f}  "
          f"clear-day MAPE {mape:.2f}%")
    return r2(ac[hold_rows], j.p[hold_rows])


def fit(temp_model, inverter=True):
    def loss(x):
        p = dict(physics.DEFAULTS, tilt=x[0], azim=x[1], pdc0=x[2],
                 shade_horizon=x[3], temp_model=temp_model, inverter=inverter)
        e = predict(p)[fit_rows] - j.p[fit_rows]
        return float((e * e).mean())
    res = minimize(loss, [10, 105, 2674, 8], method="Nelder-Mead",
                   bounds=[(0, 35), (60, 150), (2000, 3500), (0, 25)],
                   options=dict(xatol=0.05, fatol=1.0, maxiter=400))
    x = res.x
    return dict(physics.DEFAULTS, tilt=round(x[0], 1), azim=round(x[1], 1),
                pdc0=round(x[2]), shade_horizon=round(x[3], 1),
                temp_model=temp_model, inverter=inverter)


print("\n--- before (current hardcoded setup) ---")
report("sapm, no inverter, no shading", dict(physics.DEFAULTS))

print("\n--- fitted (tilt, azim, pdc0, shade horizon; pvwatts inverter) ---")
best, best_h = None, -1
for tm in ("sapm", "faiman", "pvsyst"):
    p = fit(tm)
    h = report(f"{tm:7s} {p['tilt']:.1f}deg az {p['azim']:.0f} "
               f"pdc0 {p['pdc0']:.0f} shade {p['shade_horizon']:.1f}deg", p)
    if h > best_h:
        best, best_h = p, h

json.dump(best, open("params.json", "w"), indent=1)
print(f"\nwinner ({best['temp_model']}) -> params.json")
print(json.dumps(best))
