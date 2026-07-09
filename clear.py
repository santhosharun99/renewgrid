import pandas as pd, numpy as np
d = pd.read_csv("pr_daily.csv", index_col=0, parse_dates=True)
w = pd.read_csv("weather_all.csv", parse_dates=["time"]).set_index("time")
cc = w.cloud_cover.between_time("08:00","16:00").resample("D").mean()
cc.index = cc.index.tz_localize("Asia/Kolkata")
d = d.join(cc.rename("cloud")).dropna()

for thr in (100, 40, 25, 15):
    s = d[d.cloud <= thr]
    if len(s) < 40: continue
    x = (s.index - s.index[0]).days.values
    sl = np.polyfit(x, s.PR.values, 1)[0]
    print(f"cloud<={thr:3d}%  n={len(s):3d}  PR mean {s.PR.mean():.3f}  "
          f"trend {sl*365/s.PR.mean()*100:+.2f} %/yr")

print("\nbootstrap CI on cloud<=15% bucket:")
s = d[d.cloud <= 15]
x = (s.index - s.index[0]).days.values; y = s.PR.values
sl = [np.polyfit(x[i], y[i], 1)[0] for i in
      (np.random.randint(0, len(x), len(x)) for _ in range(2000))]
sl = np.array(sl)*365/s.PR.mean()*100
print(f"  median {np.median(sl):+.2f} %/yr   95% CI [{np.percentile(sl,2.5):+.2f}, {np.percentile(sl,97.5):+.2f}]")
