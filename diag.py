import pandas as pd, numpy as np
d = pd.read_parquet("production.parquet")
d["date"] = d.t.dt.date; d["hm"] = d.t.dt.hour + d.t.dt.minute/60

def prof(y0, m0, y1, m1, label):
    m = ((d.t.dt.year==y0)&(d.t.dt.month==m0)) | ((d.t.dt.year==y1)&(d.t.dt.month==m1))
    s = d[m]
    tot = s.groupby("date").power_w.sum()
    best = tot.nlargest(6).index                     # clearest days
    p = s[s.date.isin(best)].groupby(s.hm.round(1)).power_w.mean()
    return p.rename(label)

a = prof(2024,11,2024,12,"Nov-Dec 2024")
b = prof(2025,11,2025,12,"Nov-Dec 2025")
c = pd.concat([a,b],axis=1).dropna()
c = c[c.iloc[:,0] > 50]
c["loss_%"] = (1 - c.iloc[:,1]/c.iloc[:,0])*100
print(c.round(1).to_string())
print("\nmean loss before 09:00 :", round(c[c.index<9]["loss_%"].mean(),1), "%")
print("mean loss 09:00-15:00  :", round(c[(c.index>=9)&(c.index<15)]["loss_%"].mean(),1), "%")
print("mean loss after 15:00  :", round(c[c.index>=15]["loss_%"].mean(),1), "%")
