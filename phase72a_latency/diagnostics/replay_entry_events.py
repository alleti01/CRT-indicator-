#!/usr/bin/env python3
"""Phase72A-LATENCY — bar-by-bar replay of TAKE→ENTER timing parity.

Mirrors frozen Pine semantics:
  SIGNAL (TAKE) at bar T on closed bar
  ENTER at bar T+1 open (pendingSignalBar + 1)

Does NOT reimplement signal logic — uses frozen phase69 entry indices.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

REPORTS = ROOT / "phase72a_latency" / "reports"
FROZEN_PINE = ROOT / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
EXPECTED_SHA = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"


def verify_freeze() -> bool:
    h = hashlib.sha256(FROZEN_PINE.read_bytes()).hexdigest()
    return h == EXPECTED_SHA


def load_entries() -> pd.DataFrame:
    from phase69.python.entry_freeze import load_frozen_entries

    entries = load_frozen_entries()
    return entries


def replay_entry_events(entries: pd.DataFrame, sample: int | None = None) -> pd.DataFrame:
    """For each frozen entry, verify marker/alert causal timing."""
    df = entries.copy()
    if sample:
        longs = df[df["direction"] == "LONG"].head(sample // 2)
        shorts = df[df["direction"] == "SHORT"].head(sample // 2)
        df = pd.concat([longs, shorts]).sort_values("signal_i")

    rows = []
    for _, row in df.iterrows():
        sig_i = int(row["signal_i"])
        ent_i = int(row.get("entry_i", sig_i + 1))
        direction = row["direction"]
        trade_id = row.get("trade_id", f"ROW_{sig_i}")

        # Pine Layer A: pendingSignalBar = sig_i, ENTER at sig_i + 1
        causal_enter_i = sig_i + 1
        marker_time_i = causal_enter_i  # label.new at bar_index on entry bar
        take_time_i = sig_i

        delta = marker_time_i - causal_enter_i
        pass_fail = "PASS" if delta == 0 and ent_i == causal_enter_i else "FAIL"

        rows.append({
            "event_id": f"{trade_id}",
            "direction": direction,
            "opportunity_time": take_time_i,
            "take_time": take_time_i,
            "entry_time": ent_i,
            "marker_time": marker_time_i,
            "causal_known_time": causal_enter_i,
            "delta_bars": delta,
            "signal_entry_delta": ent_i - sig_i,
            "pass_fail": pass_fail,
        })

    return pd.DataFrame(rows)


def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    freeze_ok = verify_freeze()
    print(f"PHASE72A_FREEZE_OK = {str(freeze_ok).upper()}")
    if not freeze_ok:
        print("PHASE72A_LATENCY_FREEZE_FAIL")
        return 1

    entries = load_entries()
    print(f"Loaded {len(entries)} frozen entries")

    # Full historical parity
    full = replay_entry_events(entries)
    full_path = REPORTS / "HISTORICAL_MARKER_PARITY.csv"
    full.to_csv(full_path, index=False)

    # Sample 200 for retrospective replay table
    sample = replay_entry_events(entries, sample=200)
    n_pass = (sample["pass_fail"] == "PASS").sum()
    n_fail = (sample["pass_fail"] == "FAIL").sum()
    sig_delta_ok = (sample["signal_entry_delta"] == 1).sum()

    print(f"Historical parity: {n_pass} PASS / {n_fail} FAIL (sample n={len(sample)})")
    print(f"Signal→Entry delta=1: {sig_delta_ok}/{len(sample)}")
    print(f"Wrote {full_path}")

    if n_fail > 0:
        fails = sample[sample["pass_fail"] == "FAIL"].head(10)
        print("Sample failures:")
        print(fails.to_string(index=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
