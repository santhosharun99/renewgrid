import pandas as pd, numpy as np, lightgbm as lgb, runpy, sys
sys.argv=['x']
g = runpy.run_path("model.py")   # reuse its dataframe
j, FEAT = g["j"], g["FEAT"]

# rolling-origin: train on all data before month M, test on month M
months = sorted(set(j.index.to_period("M")))[6:]
rows=[]
for mth in months:
    tr = j[j.index.to_period("M") < mth]
    te = j[j.index.to_period("M") == mth]
    if len(te) < 100: continue
    m50 = lgb.LGBMRegressor(objective='quantile', alpha=0.5, n_estimators=600, learning_rate=0.03, num_leaves=31,
                          subsample=0.8, colsample_bytree=0.8, verbose=-1)
    m50.fit(tr[FEAT], tr.target)
    pr = (te.pvlib + m50.predict(te[FEAT])).clip(lower=0)
    a = te.p.resample("D").sum()/1000
    rows.append(dict(month=str(mth),
        pvlib=(abs(a - te.pvlib.resample("D").sum()/1000)/a).mean()*100,
        hybrid=(abs(a - pr.resample("D").sum()/1000)/a).mean()*100))
r = pd.DataFrame(rows).set_index("month")
print(r.round(2).to_string())
print("\nmean  pvlib %.2f%%   hybrid %.2f%%" % (r.pvlib.mean(), r.hybrid.mean()))
print("hybrid wins in %d of %d months" % ((r.hybrid < r.pvlib).sum(), len(r)))
