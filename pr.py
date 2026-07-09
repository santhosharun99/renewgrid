import pandas as pd, numpy as np, pvlib
from scipy.optimize import minimize

LAT, LON, TZ = 10.7905, 78.7047, "Asia/Kolkata"
PDC0 = 3000          # nameplate W  (we'll sanity-check this)
GAMMA = -0.0035      # temp coeff /C

df = pd.read_parquet("production.parquet")
ph = df.set_index("t")["power_w"].resample("h").mean()

w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time")
w.index = w.index.tz_localize(TZ)
ph.index = ph.index.tz_localize(TZ)

j = pd.DataFrame({"p": ph}).join(w, how="inner").dropna()
solpos = pvlib.solarposition.get_solarposition(j.index, LAT, LON)
j["zen"], j["az"] = solpos.apparent_zenith, solpos.azimuth
dni_extra = pvlib.irradiance.get_extra_radiation(j.index)

def poa_of(tilt, azim):
    return pvlib.irradiance.get_total_irradiance(
        tilt, azim, j.zen, j.az,
        dni=j.direct_normal_irradiance, ghi=j.shortwave_radiation,
        dhi=j.diffuse_radiation, dni_extra=dni_extra, model="haydavies"
    )["poa_global"]

def model(tilt, azim, pdc0):
    poa = poa_of(tilt, azim)
    tcell = pvlib.temperature.sapm_cell(
        poa, j.temperature_2m, j.wind_speed_10m,
        **pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_polymer"])
    return pvlib.pvsystem.pvwatts_dc(poa, tcell, pdc0, GAMMA).clip(lower=0)

# fit tilt + azimuth on the sunniest first 90 days (clean baseline)
m0 = j.index < j.index[0] + pd.Timedelta(days=90)
sun = m0 & (j.shortwave_radiation > 300)

def loss(x):
    pred = model(x[0], x[1], PDC0)[sun]
    obs = j.p[sun]
    k = obs.sum() / pred.sum()          # scale-free: only shape matters
    return ((obs - k*pred)**2).mean()

res = minimize(loss, [12, 160], bounds=[(0, 35), (90, 260)], method="L-BFGS-B")
tilt, azim = res.x
print(f"fitted tilt {tilt:.1f}deg   azimuth {azim:.1f}deg  (180=south, <180=east)")

pred = model(tilt, azim, PDC0)
scale = j.p[sun].sum() / pred[sun].sum()
print(f"implied real array size: {PDC0*scale:.0f} Wp  (nameplate says {PDC0})")

j["pred"] = pred * scale
j["poa"] = poa_of(tilt, azim)

d = j[j.poa > 20].resample("D").agg(act=("p","sum"), exp=("pred","sum"), poa=("poa","sum"))
d = d[d.poa > 2000]
d["PR"] = d.act / d.exp

n = df.groupby(df.t.dt.date).size(); good = set(n[n>=130].index)
d = d[d.index.map(lambda x: x.date() in good)]
d = d[d.PR > 0.5]        # drop outage/fault days

print("\n=== monthly Performance Ratio ===")
m = d.PR.resample("ME").mean()
print(m.round(3).to_string())

print("\n=== year-over-year, matched months ===")
for mo in range(1,13):
    a = m[(m.index.month==mo) & (m.index.year<=2025) & (m.index<'2025-10')]
    b = m[(m.index.month==mo) & (m.index>='2025-10')]
    if len(a) and len(b):
        print(f"  month {mo:2d}: {a.iloc[0]:.3f} -> {b.iloc[0]:.3f}   {(b.iloc[0]/a.iloc[0]-1)*100:+.1f}%")

x = (d.index - d.index[0]).days.values
sl = np.polyfit(x, d.PR.values, 1)[0]
print(f"\nPR trend: {sl*365*100:+.2f} %-points per year")
print(f"relative: {sl*365/d.PR.mean()*100:+.2f} % per year")

d.to_csv("pr_daily.csv"); print("\nsaved pr_daily.csv")
