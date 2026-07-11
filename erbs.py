import pandas as pd, numpy as np, pvlib

LAT, LON, TZ = 10.79, 78.70, "Asia/Kolkata"

df = pd.read_parquet("production.parquet")
ph = df.set_index("t")["power_w"].resample("h").mean()
ph.index = ph.index.tz_localize(TZ)

w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time")
w.index = w.index.tz_localize(TZ)
j = pd.DataFrame({"p": ph}).join(w, how="inner").dropna()

days = pd.read_csv("days.csv", parse_dates=["date"]).set_index("date")
ok = set(days[(days.vi < days.vi.quantile(0.40)) & (days.drops <= 2)].index.date)
j = j[[d.date() in ok for d in j.index]]

sp = pvlib.solarposition.get_solarposition(j.index, LAT, LON)
dx = pvlib.irradiance.get_extra_radiation(j.index)
sun = j.shortwave_radiation > 300
r2 = lambda x: np.corrcoef(x[sun], j.p[sun])[0, 1] ** 2

# derive DNI/DHI from GHI alone
e = pvlib.irradiance.erbs(j.shortwave_radiation, sp.apparent_zenith, j.index)
print(f"Open-Meteo DNI  R2 {r2(j.direct_normal_irradiance):.4f}")
print(f"Erbs-derived DNI R2 {r2(e['dni']):.4f}\n")

def poa(dni, dhi, tilt, az):
    return pvlib.irradiance.get_total_irradiance(
        tilt, az, sp.apparent_zenith, sp.azimuth,
        dni=dni, ghi=j.shortwave_radiation, dhi=dhi,
        dni_extra=dx, model="haydavies").poa_global

print("POA R2, Open-Meteo DNI/DHI vs Erbs:")
best_om = best_er = (None, -1)
for tilt in (5, 10, 15):
    for az in (75, 90, 105, 120, 135, 150, 165, 180):
        a = r2(poa(j.direct_normal_irradiance, j.diffuse_radiation, tilt, az))
        b = r2(poa(e["dni"], e["dhi"], tilt, az))
        if a > best_om[1]: best_om = ((tilt, az), a)
        if b > best_er[1]: best_er = ((tilt, az), b)
print(f"  Open-Meteo  best {best_om[0]}  R2 {best_om[1]:.4f}")
print(f"  Erbs        best {best_er[0]}  R2 {best_er[1]:.4f}")
