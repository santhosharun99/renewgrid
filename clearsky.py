import pandas as pd, numpy as np

df = pd.read_parquet("production.parquet")
df["date"] = df.t.dt.date

rows = []
for date, g in df.groupby("date"):
    g = g.sort_values("t")
    p = g.power_w.values
    if len(g) < 130:                      # data-quality gate
        continue
    day = p[p > 50]
    if len(day) < 60:
        continue
    pk = day.max()
    if pk < 200:
        continue

    # jaggedness: mean |second difference| of the smoothed curve, normalised by peak
    s = pd.Series(day).rolling(3, center=True).mean().dropna().values
    vi = np.abs(np.diff(s, 2)).mean() / pk          # variability index

    # how boxy is the curve vs a smooth arc? area under curve / (peak * width)
    ff = day.sum() / (pk * len(day))                # fill factor

    # how many times does power drop >15% of peak in one step
    drops = int((np.diff(day) < -0.15 * pk).sum())

    rows.append(dict(date=date, kwh=p.sum()*5/60/1000, peak=pk,
                     vi=vi, ff=ff, drops=drops, n=len(g)))

d = pd.DataFrame(rows).set_index("date")

# clear = low jaggedness, no big drops
d["clear"] = (d.vi < d.vi.quantile(0.20)) & (d.drops == 0)

print(f"{len(d)} usable days,  {d.clear.sum()} classified clear ({d.clear.mean()*100:.0f}%)")
print("\nvariability index quantiles:")
print(d.vi.quantile([.1,.2,.3,.5,.8]).round(5).to_string())

print("\n--- 10 clearest days ---")
print(d.nsmallest(10, "vi")[["kwh","peak","vi","ff","drops"]].round(3).to_string())
print("\n--- 10 most variable days ---")
print(d.nlargest(10, "vi")[["kwh","peak","vi","ff","drops"]].round(3).to_string())

# cross-check against Open-Meteo cloud cover (which we do NOT use to classify)
w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time")
cc = w.cloud_cover.between_time("08:00","16:00").resample("D").mean()
cc.index = cc.index.date
d = d.join(cc.rename("cloud"))
print(f"\nmean cloud cover, days we call CLEAR : {d[d.clear].cloud.mean():.1f}%")
print(f"mean cloud cover, days we call CLOUDY: {d[~d.clear].cloud.mean():.1f}%")

d.to_csv("days.csv")
print(f"\nsaved days.csv  ({d.clear.sum()} clear days for downstream analysis)")
