"""Single-split diagnostic fit + saved quantile boosters for the API.

Physics first: pvlib (physics.py / params.json) is the pretrained model,
LightGBM learns only the residual. Data gates and outage exclusion come
from quality.py via dataset.build - never re-implement them here.
For honest accuracy numbers use backtest.py (rolling-origin); the split
here is just the last 60 days.
"""
import lightgbm as lgb
import pandas as pd
from sklearn.metrics import mean_absolute_error

import dataset

j, FEAT = dataset.build(include_aq=True)

cut = j.index.max() - pd.Timedelta(days=60)
tr, te = j[j.index <= cut], j[j.index > cut]
print(f"train {len(tr)}  test {len(te)}  features {len(FEAT)}")

KW = dict(n_estimators=600, learning_rate=0.03, num_leaves=31,
          subsample=0.8, colsample_bytree=0.8, verbose=-1)
m = lgb.LGBMRegressor(objective="l1", **KW)
m.fit(tr[FEAT], tr.target)
pred = (te.pvlib + m.predict(te[FEAT])).clip(lower=0)

# module-level m10/m50/m90 are imported by export_forecast.py
quants = {}
for a, name in ((0.1, "m10"), (0.5, "m50"), (0.9, "m90")):
    q = lgb.LGBMRegressor(objective="quantile", alpha=a, **KW)
    q.fit(tr[FEAT], tr.target)
    q.booster_.save_model(f"{name}.txt")
    globals()[name] = q
    quants[name] = (te.pvlib + q.predict(te[FEAT])).clip(lower=0)

print("\n--- hourly MAE (W) ---")
print(f"  pvlib alone      : {mean_absolute_error(te.p, te.pvlib):7.1f}")
print(f"  pvlib + LightGBM : {mean_absolute_error(te.p, pred):7.1f}")

print()
for name, s in (("pvlib", te.pvlib), ("hybrid", pred)):
    a = te.p.resample("D").sum().dropna() / 1000
    b = s.resample("D").sum().reindex(a.index) / 1000
    print(f"  daily kWh MAPE {name:7}: {(abs(a - b) / a).mean() * 100:5.2f}%")

cov = float(((te.p >= quants["m10"]) & (te.p <= quants["m90"])).mean())
print(f"\n  P10-P90 coverage on split: {cov*100:.1f}% (target 80)")

print("\n--- top features (gain) ---")
print(pd.Series(m.feature_importances_, index=FEAT)
      .sort_values(ascending=False).head(8).to_string())
print("\nsaved m10.txt m50.txt m90.txt")
