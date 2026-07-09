import pandas as pd, numpy as np

p = pd.read_excel("sep2024.xlsx")
p["t"] = pd.to_datetime(p["Updated Time"])
p["w"] = pd.to_numeric(p["Production Power(W)"], errors="coerce")

ph = p.set_index("t")["w"].resample("h").mean().to_frame("power_w")
w = pd.read_csv("weather_sep2024.csv", parse_dates=["time"]).set_index("time")

df = ph.join(w, how="inner").dropna(subset=["power_w"])
day = df[df.shortwave_radiation > 20]

print("daylight hours:", len(day))
print("\ncorrelation with power_w:")
print(day.corr()["power_w"].drop("power_w").sort_values(ascending=False).round(3))

r2 = np.corrcoef(day.shortwave_radiation, day.power_w)[0, 1] ** 2
print(f"\nR2 of GHI alone: {r2:.3f}")

d = day.resample("D").agg(
    kwh=("power_w", lambda s: s.sum() / 1000),
    ghi=("shortwave_radiation", "sum"),
    rain=("precipitation", "sum"),
    tmax=("temperature_2m", "max"),
)
d["eff"] = (d.kwh / d.ghi * 1000).round(3)
print("\n" + d.round(2).to_string())
