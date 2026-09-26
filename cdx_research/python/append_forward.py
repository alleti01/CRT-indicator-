"""Append one forward CDX observation. Never rewrite history."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

LOG = Path(__file__).resolve().parents[1] / "forward" / "forward_signal_log.csv"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--direction", required=True, choices=["LONG", "SHORT"])
    p.add_argument("--time-et", required=True, help="YYYY-MM-DD HH:MM")
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--source", default="CDX_MANUAL", choices=["CDX_MANUAL", "CDX_ALERT"])
    p.add_argument("--notes", default="")
    args = p.parse_args()
    et = datetime.strptime(args.time_et, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("America/New_York"))
    utc = et.astimezone(timezone.utc)
    line = f"{et.strftime('%Y-%m-%d %H:%M:%S')},{utc.strftime('%Y-%m-%dT%H:%M:%SZ')},NQ,1m,{args.direction},{args.price},{args.source},{args.notes}\n"
    with LOG.open("a") as fh:
        fh.write(line)
    print("appended", line.strip())


if __name__ == "__main__":
    main()
