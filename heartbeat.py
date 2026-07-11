"""Alert if the logger has gone quiet during daylight.

The LSW-3 stick is powered by the inverter, which shuts down at night -
a stale max(ts) between dusk and dawn is normal, not an outage. So the
check only fires when the sun is up (solar elevation > 5 deg).

Run manually or via launchd (com.solar.heartbeat.plist, every 30 min).
Exit codes: 0 = ok / night, 1 = stale during daylight.
"""
import sqlite3, subprocess, sys, datetime

DB = "/Users/santhosharun/solar/solar.db"
STALE_MIN = 30
LAT, LON = 10.79, 78.70


def sun_is_up(now):
    try:
        import pandas as pd
        import pvlib
        elev = pvlib.solarposition.get_solarposition(
            pd.DatetimeIndex([now], tz="Asia/Kolkata"), LAT, LON
        ).apparent_elevation.iloc[0]
        return elev > 5.0
    except Exception:
        # fallback: fixed daylight window
        return 6 <= now.hour < 19


def notify(msg):
    print(msg, file=sys.stderr, flush=True)
    try:
        subprocess.run(
            ["osascript", "-e",
             f'display notification "{msg}" with title "Solar logger"'],
            timeout=10, check=False)
    except Exception:
        pass


def main():
    now = datetime.datetime.now()
    if not sun_is_up(now):
        print(f"{now:%F %T}  night - heartbeat skipped")
        return 0
    con = sqlite3.connect(DB)
    row = con.execute("SELECT max(ts) FROM readings").fetchone()
    con.close()
    last = row[0]
    if last is None:
        notify("readings table is empty")
        return 1
    age = (now - datetime.datetime.fromisoformat(last)).total_seconds() / 60
    if age > STALE_MIN:
        notify(f"logger stale: last reading {last} ({age:.0f} min ago)")
        return 1
    print(f"{now:%F %T}  ok - last reading {age:.0f} min ago")
    return 0


if __name__ == "__main__":
    sys.exit(main())
