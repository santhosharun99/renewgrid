import pandas as pd
import lightgbm as lgb
import json
from model import FEAT, j, m10, m50, m90

latest = j.index[-1].date()
fd = j[j.index.date == latest].copy()

pred10 = (fd.pvlib + m10.predict(fd[FEAT])).clip(lower=0)
pred50 = (fd.pvlib + m50.predict(fd[FEAT])).clip(lower=0)
pred90 = (fd.pvlib + m90.predict(fd[FEAT])).clip(lower=0)

out = []
for i in range(len(fd)):
    out.append({
        "time": str(fd.index[i].time())[:5],
        "p10": float(pred10.iloc[i]),
        "p50": float(pred50.iloc[i]),
        "p90": float(pred90.iloc[i])
    })

with open("forecast.json", "w") as f:
    json.dump(out, f)
print("Forecast exported.")
