import pandas as pd, numpy as np, pvlib, lightgbm as lgb
from sklearn.metrics import mean_absolute_error

LAT, LON, TZ = 10.7905, 78.7047, "Asia/Kolkata"
TILT, AZIM = 10.0, 105.0
PDC0, GAMMA = 2674, -0.0035

df = pd.read_parquet("production.parquet")
ph = df.set_index("t")["power_w"].resample("h").mean()
ph.index = ph.index.tz_localize(TZ)

w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time")
w.index = w.index.tz_localize(TZ)

aq = pd.read_csv("aq_all.csv", parse_dates=["time"]).set_index("time")
aq.index = aq.index.tz_localize(TZ)

j = pd.DataFrame({"p": ph}).join(w, how="inner").join(aq, how="inner").dropna()

sp = pvlib.solarposition.get_solarposition(j.index, LAT, LON)
poa = pvlib.irradiance.get_total_irradiance(
    TILT, AZIM, sp.apparent_zenith, sp.azimuth,
    dni=j.direct_normal_irradiance, ghi=j.shortwave_radiation,
    dhi=j.diffuse_radiation,
    dni_extra=pvlib.irradiance.get_extra_radiation(j.index), model="haydavies")
tcell = pvlib.temperature.sapm_cell(
    poa.poa_global, j.temperature_2m, j.wind_speed_10m,
    **pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"]["open_rack_glass_polymer"])
j["pvlib"] = pvlib.pvsystem.pvwatts_dc(poa.poa_global, tcell, PDC0, GAMMA).clip(lower=0)
j["poa"] = poa.poa_global
j["poa_direct"] = poa.poa_direct
j["zenith"] = sp.apparent_zenith
j["azimuth"] = sp.azimuth

days = pd.read_csv("days.csv", parse_dates=["date"]).set_index("date")
days["clear"] = (days.vi < days.vi.quantile(0.40)) & (days.drops <= 2)
print(f"clear days (loosened): {days.clear.sum()}")

ok = set(days.index.date)
j = j[[d.date() in ok for d in j.index]]
j = j[j.poa > 20]

dd = j.resample("D").agg(a=("p","sum"), e=("pvlib","sum"))
bad = set(dd[(dd.a / dd.e) < 0.5].index.date)
print(f"dropping {len(bad)} outage/fault days: {sorted(bad)}")
j = j[[d.date() not in bad for d in j.index]]

j["hour"] = j.index.hour + j.index.minute/60
j["doy"] = j.index.dayofyear
j["doy_sin"], j["doy_cos"] = np.sin(2*np.pi*j.doy/365), np.cos(2*np.pi*j.doy/365)
j["clearness"] = (j.shortwave_radiation / (j.poa+1)).clip(0, 2)
j["target"] = j.p - j.pvlib

FEAT = ["pvlib","poa","poa_direct","shortwave_radiation","direct_normal_irradiance",
        "diffuse_radiation","temperature_2m","cloud_cover","wind_speed_10m",
        "precipitation","hour","doy_sin","doy_cos","zenith","azimuth","clearness",
        "pm10","pm2_5","aerosol_optical_depth","dust"]

cut = j.index.max() - pd.Timedelta(days=60)
tr, te = j[j.index <= cut], j[j.index > cut]
print(f"\ntrain {len(tr)}  test {len(te)}")

m = lgb.LGBMRegressor(n_estimators=600, learning_rate=0.03, num_leaves=31,
                      subsample=0.8, colsample_bytree=0.8, verbose=-1)
m10 = lgb.LGBMRegressor(objective='quantile', alpha=0.1, n_estimators=600, learning_rate=0.03, num_leaves=31, subsample=0.8, colsample_bytree=0.8, verbose=-1)
m50 = lgb.LGBMRegressor(objective='quantile', alpha=0.5, n_estimators=600, learning_rate=0.03, num_leaves=31, subsample=0.8, colsample_bytree=0.8, verbose=-1)
m90 = lgb.LGBMRegressor(objective='quantile', alpha=0.9, n_estimators=600, learning_rate=0.03, num_leaves=31, subsample=0.8, colsample_bytree=0.8, verbose=-1)

m.fit(tr[FEAT], tr.target)
m10.fit(tr[FEAT], tr.target)
m50.fit(tr[FEAT], tr.target)
m90.fit(tr[FEAT], tr.target)

pred = (te.pvlib + m.predict(te[FEAT])).clip(lower=0)
pred10 = (te.pvlib + m10.predict(te[FEAT])).clip(lower=0)
pred50 = (te.pvlib + m50.predict(te[FEAT])).clip(lower=0)
pred90 = (te.pvlib + m90.predict(te[FEAT])).clip(lower=0)

m10.booster_.save_model("m10.txt")
m50.booster_.save_model("m50.txt")
m90.booster_.save_model("m90.txt")

print("\n--- hourly MAE (W) ---")
print(f"  pvlib alone      : {mean_absolute_error(te.p, te.pvlib):7.1f}")
print(f"  pvlib + LightGBM : {mean_absolute_error(te.p, pred):7.1f}")

print()
for name, s in (("pvlib", te.pvlib), ("hybrid", pred)):
    a = te.p.resample("D").sum()/1000; b = s.resample("D").sum()/1000
    print(f"  daily kWh MAPE {name:7}: {(abs(a-b)/a).mean()*100:5.2f}%")

print("\n--- top features ---")
print(pd.Series(m.feature_importances_, index=FEAT).sort_values(ascending=False).head(8).to_string())
