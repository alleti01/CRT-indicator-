#!/usr/bin/env python3
"""Prefix-invariance replay proxy for Phase72A Layer A causality (no Pine edits)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PINE = ROOT / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
EXPECTED_SHA = "d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f"
OUT = ROOT / "phase72a_causality" / "reports" / "REPLAY_GATE_CAUSALITY.json"

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.tools.run_phase72b_parity import events_to_dataframe, prefix_invariance_test, window_indices


WINDOWS = [
    ("aug28_session", "2026-08-28 08:30", "2026-08-28 16:00"),
    ("aug30_chi_evening", "2026-08-30 17:00", "2026-08-30 22:30"),
]


def verify_freeze() -> bool:
    return hashlib.sha256(PINE.read_bytes()).hexdigest() == EXPECTED_SHA


def signal_timing(df: pd.DataFrame) -> list[dict]:
    rows = []
    sig_mask = df["signal_long"] | df["signal_short"]
    for i in df.index[sig_mask]:
        r = df.loc[i]
        bi = int(r["bar_index"])
        side = "LONG" if r["signal_long"] else "SHORT"
        enter_same = bool(r["enter_long"] if side == "LONG" else r["enter_short"])
        nxt = df[(df["bar_index"] == bi + 1)]
        enter_nxt = False
        if len(nxt):
            nr = nxt.iloc[0]
            enter_nxt = bool(nr["enter_long"] if side == "LONG" else nr["enter_short"])
        rows.append(
            {
                "bar_index": bi,
                "timestamp": str(r["timestamp"]),
                "direction": side,
                "enter_on_signal_bar": enter_same,
                "enter_on_next_bar": enter_nxt,
                "causal_ok": (not enter_same) and enter_nxt,
            }
        )
    return rows


def main() -> int:
    if not verify_freeze():
        print("FREEZE_SHA_MISMATCH", file=sys.stderr)
        return 1

    m1, m5, m15 = load_markets_lw()
    results = {"freeze_ok": True, "windows": []}

    for wid, start, end in WINDOWS:
        try:
            s_i, e_i = window_indices(m1, start, end)
            pref = prefix_invariance_test(m1, m5, m15, s_i, e_i)
            _, ev, _, _ = run_mirror(m1, m5, m15, s_i, e_i)
            df = events_to_dataframe(ev)
            timing = signal_timing(df)
            causal_ok = sum(1 for t in timing if t["causal_ok"])
            results["windows"].append(
                {
                    "id": wid,
                    "start": start,
                    "end": end,
                    "bars": e_i - s_i,
                    "prefix_invariance": pref,
                    "signal_count": len(timing),
                    "signal_entry_causal_ok": causal_ok,
                    "signal_entry_violations": len(timing) - causal_ok,
                    "sample_signals": timing[:8],
                }
            )
        except Exception as ex:
            results["windows"].append({"id": wid, "error": str(ex)})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(json.dumps(results, indent=2, default=str))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
