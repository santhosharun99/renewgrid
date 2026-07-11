import pandas as pd, numpy as np, pvlib
LAT, LON, TZ = 10.79, 78.70, "Asia/Kolkata"
df = pd.read_parquet("production.parquet")
w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time")
w.index = w.index.tz_localize(TZ)
days = pd.read_csv("days.csv", parse_dates=["date"]).set_index("date")
ok = set(days[(days.vi < days.vi.quantile(0.40)) & (days.drops <= 2)].index.date)

for shift in (-2, -1, 0, 1, 2):
    ph = df.set_index("t")["power_w"].resample("h").mean()
    ph.index = ph.index.tz_localize(TZ) + pd.Timedelta(hours=shift)
    j = pd.DataFrame({"p": ph}).join(w, how="inner").dropna()
    j = j[[d.date() in ok for d in j.index]]
    sun = j.shortwave_radiation > 300
    if sun.sum() < 100: continue
    r = np.corrcoef(j.shortwave_radiation[sun], j.p[sun])[0,1]**2
    print(f"shift {shift:+d} h   n={sun.sum():5d}   GHI R2 {r:.4f}")
