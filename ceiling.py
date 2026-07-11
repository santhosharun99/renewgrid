import pandas as pd, numpy as np, pvlib
LAT, LON, TZ = 10.79, 78.70, "Asia/Kolkata"
df = pd.read_parquet("production.parquet")
ph = df.set_index("t")["power_w"].resample("h").mean(); ph.index = ph.index.tz_localize(TZ)
w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time"); w.index = w.index.tz_localize(TZ)
j0 = pd.DataFrame({"p": ph}).join(w, how="inner").dropna()
days = pd.read_csv("days.csv", parse_dates=["date"]).set_index("date")

for q, label in ((0.05,"top 5%"), (0.10,"top 10%"), (0.20,"top 20%"), (0.40,"top 40%"), (1.0,"all days")):
    ok = set(days[days.vi <= days.vi.quantile(q)].index.date)
    j = j0[[d.date() in ok for d in j0.index]]
    sp = pvlib.solarposition.get_solarposition(j.index, LAT, LON)
    dx = pvlib.irradiance.get_extra_radiation(j.index)
    poa = pvlib.irradiance.get_total_irradiance(10, 105, sp.apparent_zenith, sp.azimuth,
        dni=j.direct_normal_irradiance, ghi=j.shortwave_radiation,
        dhi=j.diffuse_radiation, dni_extra=dx, model="haydavies").poa_global
    sun = j.shortwave_radiation > 300
    if sun.sum() < 50: continue
    r = np.corrcoef(poa[sun], j.p[sun])[0,1]**2
    # exclude the shading window
    ns = sun & (j.index.hour >= 9)
    r2 = np.corrcoef(poa[ns], j.p[ns])[0,1]**2
    print(f"{label:9}  n={sun.sum():5d}   POA R2 {r:.4f}   after 09:00 only {r2:.4f}")
