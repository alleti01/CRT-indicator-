"""Summarize the shadow ATR profiles from phase74/logs/shadow_profiles.jsonl.

    python -m phase74.tools.shadow_profile_report
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="phase74/logs/shadow_profiles.jsonl")
    args = ap.parse_args()
    path = Path(args.log)
    if not path.exists():
        print(f"No shadow profile log yet at {path}")
        return
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    by = defaultdict(list)
    for r in rows:
        by[r["profile"]].append(r)
    for name, rs in by.items():
        closes = [r for r in rs if r["event"] == "CLOSE"]
        skips = Counter(r["reason"] for r in rs if r["event"] == "SKIP")
        opens = [r for r in rs if r["event"] == "OPEN"]
        wins = [r for r in closes if r["usd"] > 0]
        print(f"\n== {name}")
        print(f"signals seen: {len(opens) + sum(skips.values())}   trades: {len(opens)}   closed: {len(closes)}   open now: {len(opens) - len(closes)}")
        if closes:
            print(f"win rate: {len(wins) / len(closes):.0%}   total R: {sum(r['r'] for r in closes):+.2f}   "
                  f"P&L: ${sum(r['usd'] for r in closes):+,.0f}   balance: ${closes[-1]['balance']:+,.0f}   eval: {closes[-1]['eval_status']}")
        if skips:
            print("skipped: " + ", ".join(f"{k} {v}" for k, v in skips.most_common()))
        for r in closes[-5:]:
            print(f"  {r['exit_time_utc'][:16]} {r['direction']:5} {r['exit_reason']:6} {r['r']:+.2f}R ${r['usd']:+,.0f}")


if __name__ == "__main__":
    main()
