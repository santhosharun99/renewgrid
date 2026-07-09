import pandas as pd
import sqlite3

def classify_day(date_str):
    date = pd.to_datetime(date_str).date()
    
    daily = pd.read_csv("daily.csv", index_col=0, parse_dates=True)
    if date not in daily.index.date:
        return "No Data"
        
    row = daily[daily.index.date == date].iloc[0]
    
    # The two criteria: eff-ratio < 0.6 OR a/e < 0.5
    # Since daily.csv has ratio, we use it. We'll use 0.6 as a threshold for a severe drop.
    is_outage_candidate = row.get("ratio", 1.0) < 0.6
    
    con = sqlite3.connect("solar.db")
    cur = con.cursor()
    cur.execute("SELECT v1, v2, v3 FROM readings WHERE ts LIKE ?", (f"{date_str}%",))
    rows = cur.fetchall()
    
    if len(rows) > 0:
        import numpy as np
        v_mean = np.mean([r for r in rows if r[0] is not None and r[1] is not None])
        if is_outage_candidate:
            if v_mean < 50:
                return "Grid Outage (Confirmed via Voltage)"
            else:
                return "Inverter Fault (Voltage Present)"
        else:
            return "Normal"
    else:
        if is_outage_candidate:
            return "Grid Outage / Fault (Historic, No Voltage Data)"
        else:
            return "Normal"

if __name__ == "__main__":
    print("Test on 2024-09-20:", classify_day("2024-09-20"))
