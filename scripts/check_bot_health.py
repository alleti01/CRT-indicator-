"""Decide whether to alert the user about the bot PC. Prints one JSON line: {"notify": bool, "message": str, ...}.

Problems:
- SYNC_DOWN: no new commit on origin/bot-logs for over 45 minutes (the PC syncs every 30).
- BARS_STALE: market open and the newest bar is over 15 minutes old.
- BOT_NOT_RUNNING: the PC's last health check found no run_live process.

Notifies when a problem appears, again every 2 hours while it lasts, and once when it clears.
State lives in phase74/logs/bot_alert_state.json (gitignored). Read-only otherwise.

    python3 scripts/check_bot_health.py
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "phase74" / "logs" / "bot_alert_state.json"
ET = ZoneInfo("America/New_York")
SYNC_LIMIT = timedelta(minutes=45)
BAR_LIMIT = timedelta(minutes=15)
REMIND_EVERY = timedelta(hours=2)


def market_open(now: datetime) -> bool:
    et = now.astimezone(ET)
    d, h = et.weekday(), et.hour  # Monday = 0
    if d == 5:
        return False
    if d == 4 and h >= 17:
        return False
    if d == 6 and h < 18:
        return False
    return h != 17  # daily 5-6 pm ET break


def parse_ts(ts: str) -> datetime:
    """PowerShell writes 7 fractional digits; Python 3.9 accepts at most 6."""
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", ts.strip()))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def problems(now: datetime) -> tuple[list[str], dict]:
    git("fetch", "--quiet", "origin", "bot-logs")
    synced = parse_ts(git("log", "-1", "--format=%cI", "origin/bot-logs")).astimezone(timezone.utc)
    health = json.loads(git("show", "origin/bot-logs:health.json").lstrip("﻿"))
    last_bar = parse_ts(health["last_bar_utc"]) if health.get("last_bar_utc") else None
    out = []
    if now - synced > SYNC_LIMIT:
        out.append("SYNC_DOWN")
    if market_open(now) and (last_bar is None or now - last_bar > BAR_LIMIT):
        out.append("BARS_STALE")
    if not health.get("bot_running", False):
        out.append("BOT_NOT_RUNNING")
    info = {
        "last_sync_et": synced.astimezone(ET).strftime("%a %-I:%M %p"),
        "last_bar_et": last_bar.astimezone(ET).strftime("%a %-I:%M %p") if last_bar else "none",
        "market_open": market_open(now),
    }
    return out, info


def message(probs: list[str], info: dict) -> str:
    parts = []
    if "SYNC_DOWN" in probs:
        parts.append(f"log sync stopped (last {info['last_sync_et']} ET), PC may be off or offline")
    if "BARS_STALE" in probs:
        parts.append(f"no bars since {info['last_bar_et']} ET")
    if "BOT_NOT_RUNNING" in probs:
        parts.append("bot process not running")
    return "Trading bot: " + "; ".join(parts)


def main() -> int:
    now = datetime.now(timezone.utc)
    try:
        probs, info = problems(now)
    except Exception as exc:  # can't reach GitHub or branch missing: treat as a sync problem
        probs, info = ["CHECK_FAILED"], {"error": str(exc)[:200]}
    try:
        state = json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        state = {"problems": [], "last_notified_utc": None}
    before = set(state.get("problems", []))
    last = datetime.fromisoformat(state["last_notified_utc"]) if state.get("last_notified_utc") else None

    notify, text = False, ""
    if probs:
        if set(probs) - before or last is None or now - last >= REMIND_EVERY:
            notify = True
            text = ("Trading bot: health check couldn't read GitHub: " + info.get("error", "")) if probs == ["CHECK_FAILED"] else message(probs, info)
            if set(probs) <= before and last is not None:
                text = "Still down. " + text
    elif before:
        notify = True
        text = f"Trading bot recovered: syncing and bars flowing (last bar {info['last_bar_et']} ET)"

    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "problems": probs,
        "last_notified_utc": now.isoformat() if notify else state.get("last_notified_utc"),
        "checked_utc": now.isoformat(),
    }))
    print(json.dumps({"notify": notify, "message": text[:190], "problems": probs, **info}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
