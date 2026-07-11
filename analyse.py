import pandas as pd, requests

import quality

LAT, LON = 10.79, 78.70
df = quality.load_production()
d0, d1 = df.t.min().date(), df.t.max().date()

print(f"fetching weather {d0} -> {d1} ...")
r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
    "latitude": LAT, "longitude": LON, "start_date": str(d0), "end_date": str(d1),
    "hourly": "shortwave_radiation,direct_normal_irradiance,diffuse_radiation,"
              "temperature_2m,cloud_cover,wind_speed_10m,precipitation",
    "timezone": "Asia/Kolkata"}, timeout=60)
r.raise_for_status()
w = pd.DataFrame(r.json()["hourly"]); w["time"] = pd.to_datetime(w["time"])
w.to_csv("weather_all.csv", index=False)
print("weather rows:", len(w))

# hourly production
ph = df.set_index("t")["power_w"].resample("h").mean().to_frame("power_w")
j = ph.join(w.set_index("time"), how="inner")

good = quality.usable_days(df)   # shared gate - do not re-implement

daily = j.resample("D").agg(
    kwh=("power_w", lambda s: s.sum()/1000),
    ghi=("shortwave_radiation","sum"),
    rain=("precipitation","sum"),
    tmax=("temperature_2m","max"),
)
daily = daily[daily.index.map(lambda x: x.date() in good)]
daily = daily[daily.ghi > 2000]
daily["eff"] = daily.kwh / daily.ghi * 1000

# outage/fault/gap days come from outage_classifier.py (events.csv),
# not from a local eff-ratio heuristic
daily = quality.exclude_events(daily)

daily["eff30"] = daily.eff.rolling(30, center=True, min_periods=10).quantile(0.90)

print("\n=== monthly mean eff (clear-ish days only) ===")
top = daily[daily.eff > daily.eff.rolling(15, center=True, min_periods=5).quantile(0.75)]
print(top.eff.resample("ME").mean().round(3).to_string())

print("\n=== worst 15 remaining days (eff vs local 90th pct) ===")
print("(known events already excluded via events.csv)")
daily["ratio"] = daily.eff / daily.eff30
print(daily.nsmallest(15, "ratio")[["kwh","ghi","rain","eff","eff30","ratio"]].round(2).to_string())

print("\n=== rain events > 10mm, eff before vs after ===")
for day in daily[daily.rain > 10].index:
    pre = daily.eff.loc[:day].tail(6)[:-1]
    post = daily.eff.loc[day:].head(6)[1:]
    if len(pre) >= 3 and len(post) >= 3:
        print(f"{day.date()}  rain {daily.rain[day]:5.1f}mm   "
              f"eff before {pre.mean():.3f}  after {post.mean():.3f}  "
              f"change {(post.mean()/pre.mean()-1)*100:+.1f}%")

daily.to_csv("daily.csv")
print("\nsaved daily.csv")
