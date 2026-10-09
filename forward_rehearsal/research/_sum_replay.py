import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

blob = json.loads(Path("forward_rehearsal/reports/last_week_cdx/replay_blob.json").read_text(encoding="utf-8"))
print("id side sw class | s1 5 / 10 / 20")
for x in blob:
    parts = []
    for n in (5, 10, 20):
        p, w = x["sys" + str(n)]["s1"]
        parts.append(f"{None if p is None else round(p, 1)}:{w}")
    print(x["id"], x["side"], x["sideways"], x["class"], " | ".join(parts))

entry = 31051.75
t0 = datetime(2026, 9, 23, 6, 7, tzinfo=timezone.utc)
mfe = 0.0
first = hit5 = hit10 = hit20 = None
s5, s10, s20 = 31026.11, 31020.36, 31018.36
for row in csv.DictReader(open("phase74/logs/bars.csv", encoding="utf-8")):
    t = datetime.fromisoformat(row["timestamp_utc"])
    if t <= t0 or t > t0 + timedelta(hours=8):
        continue
    h, l = float(row["high"]), float(row["low"])
    mfe = max(mfe, h - entry)
    if first is None and h >= entry + 7:
        first = (t.isoformat(), round(mfe, 2))
    if hit5 is None and l <= s5:
        hit5 = (t.isoformat(), round(mfe, 2))
    if hit10 is None and l <= s10:
        hit10 = (t.isoformat(), round(mfe, 2))
    if hit20 is None and l <= s20:
        hit20 = (t.isoformat(), round(mfe, 2))
print("WED first+7", first)
print("WED hit5", hit5)
print("WED hit10", hit10)
print("WED hit20", hit20)
print("WED mfe8h", round(mfe, 2))
