import pandas as pd, glob, sqlite3

files = sorted(glob.glob("data/*.xlsx"))
print(f"found {len(files)} files")

frames = []
for f in files:
    d = pd.read_excel(f)
    d["t"] = pd.to_datetime(d["Updated Time"])
    d["power_w"] = pd.to_numeric(d["Production Power(W)"], errors="coerce")
    frames.append(d[["t", "power_w"]])
    print(f"  {f.split('/')[-1][-12:]:14} {len(d):6d} rows  {d.t.min().date()} -> {d.t.max().date()}")

df = pd.concat(frames).dropna().drop_duplicates("t").sort_values("t").reset_index(drop=True)

print(f"\nTOTAL {len(df):,} rows")
print(f"range {df.t.min()} -> {df.t.max()}")
print(f"span  {(df.t.max()-df.t.min()).days} days")

# coverage check
days = df.groupby(df.t.dt.date).size()
full = pd.date_range(df.t.min().date(), df.t.max().date(), freq="D").date
missing = sorted(set(full) - set(days.index))
print(f"\ndays with data: {len(days)} / {len(full)}   missing: {len(missing)}")
if missing:
    print("missing days:", missing[:15], "..." if len(missing) > 15 else "")
thin = days[days < 100]
print(f"\ndays with <100 samples (expect ~150): {len(thin)}")
if len(thin): print(thin.head(20).to_string())

df.to_parquet("production.parquet")
con = sqlite3.connect("solar.db")
df.to_sql("production_history", con, if_exists="replace", index=False)
con.close()
print("\nsaved -> production.parquet + solar.db:production_history")
