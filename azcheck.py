import pandas as pd, numpy as np, pvlib
LAT, LON, TZ = 10.79, 78.70, "Asia/Kolkata"
df = pd.read_parquet("production.parquet")
ph = df.set_index("t")["power_w"].resample("h").mean(); ph.index = ph.index.tz_localize(TZ)
w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time"); w.index = w.index.tz_localize(TZ)
j = pd.DataFrame({"p": ph}).join(w, how="inner").dropna()
sp = pvlib.solarposition.get_solarposition(j.index, LAT, LON)
dx = pvlib.irradiance.get_extra_radiation(j.index)
sun = j.shortwave_radiation > 300
for az in (90, 120, 150, 180, 210):
    poa = pvlib.irradiance.get_total_irradiance(12.1, az, sp.apparent_zenith, sp.azimuth,
        dni=j.direct_normal_irradiance, ghi=j.shortwave_radiation,
        dhi=j.diffuse_radiation, dni_extra=dx, model="haydavies").poa_global
    k = j.p[sun].sum()/poa[sun].sum()
    r = np.corrcoef(poa[sun], j.p[sun])[0,1]**2
    print(f"az {az:3d}  R2 {r:.4f}   implied Wp {k*1000*(3000/1000)/ (j.p[sun].sum()/pvlib.pvsystem.pvwatts_dc(poa,25,3000,-0.0035).clip(lower=0)[sun].sum()) :.0f}" if False else f"az {az:3d}  R2 {r:.4f}")
