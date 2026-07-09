"""Task 6: how much does each factor matter?

One LightGBM on *raw* hourly power with all features (physics, weather,
calendar, air quality) + shap.TreeExplainer. Attribution comes from SHAP on
the single model — never one-model-per-factor (confounding: temperature
correlates +0.34 with power via sunshine while its causal effect is
negative).

This answers the *attenuation* question for aerosols (does today's AOD/PM
reduce today's output?). The *deposition* hypothesis (cumulative dust) was
killed separately — PM10 lost significance once days-since-rain was
controlled.
"""
import numpy as np
import pandas as pd
import lightgbm as lgb
import shap

import dataset

j, FEAT = dataset.build(include_aq=True)
X, y = j[FEAT], j.p

m = lgb.LGBMRegressor(n_estimators=600, learning_rate=0.03, num_leaves=31,
                      subsample=0.8, colsample_bytree=0.8, verbose=-1)
m.fit(X, y)

sv = shap.TreeExplainer(m).shap_values(X)
t = pd.DataFrame({
    "mean_abs_shap_W": np.abs(sv).mean(axis=0),
    "mean_signed_shap_W": sv.mean(axis=0),
}, index=FEAT)
t["pct_of_total"] = t.mean_abs_shap_W / t.mean_abs_shap_W.sum() * 100
t = t.sort_values("mean_abs_shap_W", ascending=False)

print(f"n = {len(j)} daylight hours, model R2 (in-sample) "
      f"{m.score(X, y):.4f}\n")
print(t.round(2).to_string())

aq = t.loc[[f for f in dataset.AQ_FEAT if f in t.index]]
print(f"\nair-quality features combined: {aq.mean_abs_shap_W.sum():.1f} W "
      f"({aq.pct_of_total.sum():.2f}% of total attribution)")
t.to_csv("shap_attribution.csv")
print("saved shap_attribution.csv")
