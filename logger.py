from pysolarmanv5 import PySolarmanV5
import sqlite3, time, datetime, sys

IP, SERIAL, DB = "192.168.29.238", 2787693150, "solar.db"

REGS = {
    "yield_today": (60, 0.1), "ac_power": (109, 1), "dc_power": (96, 0.1),
    "freq": (79, 0.01), "v1": (73, 0.1), "v2": (74, 0.1), "v3": (75, 0.1),
    "i1": (76, 0.1), "i2": (77, 0.1), "i3": (78, 0.1),
    "r90": (90, 1), "r91": (91, 1), "r145": (145, 1), "r146": (146, 1),
    "r123": (123, 1), "r126": (126, 1), "r138": (138, 1),
}

db = sqlite3.connect(DB)
db.execute("""CREATE TABLE IF NOT EXISTS readings (
    ts TEXT PRIMARY KEY, total_yield REAL,
    """ + ", ".join(f"{k} REAL" for k in REGS) + ")")
db.commit()

def read():
    inv = PySolarmanV5(IP, SERIAL, port=8899, mb_slave_id=1, socket_timeout=10)
    try:
        block = {}
        for start in (60, 70, 90, 120, 140):
            for i, v in enumerate(inv.read_holding_registers(register_addr=start, quantity=20)):
                block[start + i] = v
        row = {k: block[a] * s for k, (a, s) in REGS.items() if a in block}
        row["total_yield"] = (block[64] * 65536 + block[63]) * 0.1
        return row
    finally:
        try: inv.disconnect()
        except Exception: pass

while True:
    try:
        row = read()
        row["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        cols = ",".join(row)
        db.execute(f"INSERT OR REPLACE INTO readings ({cols}) VALUES ({','.join('?'*len(row))})",
                   list(row.values()))
        db.commit()
        print(f"{row['ts']}  {row['ac_power']:.0f}W  today {row['yield_today']:.1f}kWh", flush=True)
    except Exception as e:
        print(f"{datetime.datetime.now():%H:%M:%S}  ERR {e}", file=sys.stderr, flush=True)
    time.sleep(300)
