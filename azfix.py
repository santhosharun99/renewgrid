import pandas as pd, numpy as np, pvlib
LAT, LON, TZ = 10.79, 78.70, "Asia/Kolkata"
df = pd.read_parquet("production.parquet")
ph = df.set_index("t")["power_w"].resample("h").mean(); ph.index = ph.index.tz_localize(TZ)
w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time"); w.index = w.index.tz_localize(TZ)
j = pd.DataFrame({"p": ph}).join(w, how="inner").dropna()

# clear-ish, non-outage days only
days = pd.read_csv("days.csv", parse_dates=["date"]).set_index("date")
ok = set(days[(days.vi < days.vi.quantile(0.40)) & (days.drops <= 2)].index.date)
j = j[[d.date() in ok for d in j.index]]

sp = pvlib.solarposition.get_solarposition(j.index, LAT, LON)
dx = pvlib.irradiance.get_extra_radiation(j.index)
sun = j.shortwave_radiation > 300
print(f"n = {sun.sum()} sunny hours on clear-ish days\n")

print(f"BASELINE  raw GHI      R2 {np.corrcoef(j.shortwave_radiation[sun], j.p[sun])[0,1]**2:.4f}")
print(f"BASELINE  raw DNI      R2 {np.corrcoef(j.direct_normal_irradiance[sun], j.p[sun])[0,1]**2:.4f}\n")

best = (None, -1)
for tilt in (5, 10, 15, 20):
    for az in (60, 75, 90, 105, 120, 135, 150, 165, 180):
        poa = pvlib.irradiance.get_total_irradiance(tilt, az, sp.apparent_zenith, sp.azimuth,
            dni=j.direct_normal_irradiance, ghi=j.shortwave_radiation,
            dhi=j.diffuse_radiation, dni_extra=dx, model="haydavies").poa_global
        r = np.corrcoef(poa[sun], j.p[sun])[0,1]**2
        if r > best[1]: best = ((tilt, az), r)
    print(f"tilt {tilt:2d}  best so far {best[0]}  R2 {best[1]:.4f}")

print(f"\nBEST: tilt {best[0][0]}, azimuth {best[0][1]}, R2 {best[1]:.4f}")
