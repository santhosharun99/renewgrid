import requests, pandas as pd

LAT, LON = 10.7905, 78.7047
START, END = "2024-09-01", "2024-09-30"

r = requests.get("https://archive-api.open-meteo.com/v1/archive", params={
    "latitude": LAT, "longitude": LON,
    "start_date": START, "end_date": END,
    "hourly": "shortwave_radiation,direct_normal_irradiance,diffuse_radiation,"
              "temperature_2m,cloud_cover,wind_speed_10m,precipitation",
    "timezone": "Asia/Kolkata",
})
r.raise_for_status()
w = pd.DataFrame(r.json()["hourly"])
w["time"] = pd.to_datetime(w["time"])
w.to_csv("weather_sep2024.csv", index=False)
print("saved", w.shape)
