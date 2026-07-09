import pandas as pd
import numpy as np
from scipy.stats import linregress

# Read PR
pr = pd.read_csv("pr_daily.csv", index_col=0, parse_dates=True)
if pr.index.tz is not None:
    pr.index = pr.index.tz_convert("Asia/Kolkata").date
else:
    pr.index = pr.index.date
pr.index = pd.to_datetime(pr.index)

# Read Days
days = pd.read_csv("days.csv", parse_dates=["date"]).set_index("date")
days.index = pd.to_datetime(days.index)

# Read AQ data
aq = pd.read_csv("aq_all.csv", parse_dates=["time"])
if aq["time"].dt.tz is not None:
    aq["date"] = aq["time"].dt.tz_convert("Asia/Kolkata").dt.date
else:
    aq["date"] = aq["time"].dt.date
aq_daily = aq.groupby("date")[["pm10", "pm2_5", "dust", "aerosol_optical_depth"]].mean()
aq_daily.index = pd.to_datetime(aq_daily.index)

# Read weather
w = pd.read_csv("weather_all.csv", parse_dates=["time"])
if w["time"].dt.tz is not None:
    w["date"] = w["time"].dt.tz_convert("Asia/Kolkata").dt.date
else:
    w["date"] = w["time"].dt.date
rain_daily = w.groupby("date")[["precipitation"]].sum()
rain_daily.index = pd.to_datetime(rain_daily.index)

# Join
df = pr.join(days, how="inner").join(aq_daily, how="inner").join(rain_daily, how="inner").sort_index()
pr_col = "PR" if "PR" in df.columns else "pr"

cumulative_dust = []
cumulative_pm10 = []
curr_dust = 0
curr_pm10 = 0

for idx, row in df.iterrows():
    if row["precipitation"] > 5.0:
        curr_dust = 0
        curr_pm10 = 0
    else:
        curr_dust += row.get("dust", 0) if not pd.isna(row.get("dust")) else 0
        curr_pm10 += row.get("pm10", 0) if not pd.isna(row.get("pm10")) else 0
    cumulative_dust.append(curr_dust)
    cumulative_pm10.append(curr_pm10)

df["cum_dust"] = cumulative_dust
df["cum_pm10"] = cumulative_pm10

import quality
clear = quality.clear_days(days)  # shared gate (vi < q40, drops <= 2)
df_clear = df[[d.date() in clear for d in df.index]].dropna(subset=[pr_col, "cum_dust"])

print(f"Clear days count (for deposition exp): {len(df_clear)}")
print(f"Correlation (PR vs Cum Dust): {df_clear[pr_col].corr(df_clear['cum_dust']):.4f}")
print(f"Correlation (PR vs Cum PM10): {df_clear[pr_col].corr(df_clear['cum_pm10']):.4f}")

res_dust = linregress(df_clear["cum_dust"], df_clear[pr_col])
res_pm10 = linregress(df_clear["cum_pm10"], df_clear[pr_col])

print("\n--- Regression: PR vs Cumulative Dust ---")
print(f"Slope (PR loss per unit dust): {res_dust.slope:.6e}")
print(f"R-squared: {res_dust.rvalue**2:.4f}")
print(f"P-value: {res_dust.pvalue:.4e}")

print("\n--- Regression: PR vs Cumulative PM10 ---")
print(f"Slope (PR loss per unit PM10): {res_pm10.slope:.6e}")
print(f"R-squared: {res_pm10.rvalue**2:.4f}")
print(f"P-value: {res_pm10.pvalue:.4e}")
