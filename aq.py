import requests, pandas as pd

LAT, LON = 10.7905, 78.7047
START, END = "2024-10-01", "2026-07-09"

r = requests.get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
    "latitude": LAT, "longitude": LON,
    "start_date": START, "end_date": END,
    "hourly": "pm10,pm2_5,aerosol_optical_depth,dust",
    "timezone": "Asia/Kolkata",
})
r.raise_for_status()
w = pd.DataFrame(r.json()["hourly"])
w["time"] = pd.to_datetime(w["time"])
w.to_csv("aq_all.csv", index=False)
print("saved aq_all.csv with shape", w.shape)
