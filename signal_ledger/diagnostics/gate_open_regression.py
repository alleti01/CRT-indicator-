#!/usr/bin/env python3
"""Before/after gate_open branch comparison (inline vs var-gated).

Uses the Phase72B Python mirror with ``gate_snap_mode`` on the same padded
run path as ``run_mirror``. Pre-refactor (inline ``if``) vs post-refactor
(``gate_snap := cond; if gate_snap``).

NOT TradingView Pine execution — labels output accordingly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.python.event_log import events_to_dataframe
from phase72b.tools.run_phase72b_parity import window_indices

OUT = ROOT / "signal_ledger" / "reports" / "GATE_OPEN_REGRESSION.json"

SIGNAL_COLS = ("signal_long", "signal_short", "enter_long", "enter_short")

WINDOWS = [
    ("aug28_session", "2026-08-28 08:30", "2026-08-28 16:00"),
    ("jul_aug_2026", "2026-07-01 00:00", "2026-08-28 23:59"),
]


def _compare(pre_df: pd.DataFrame, post_df: pd.DataFrame) -> dict:
    merged = pre_df.merge(
        post_df,
        on="bar_index",
        suffixes=("_pre", "_post"),
        how="outer",
    )
    mismatches = []
    for _, row in merged.iterrows():
        diffs = {}
        for col in SIGNAL_COLS:
            pre_v = bool(row.get(f"{col}_pre", False))
            post_v = bool(row.get(f"{col}_post", False))
            if pre_v != post_v:
                diffs[col] = {"pre": pre_v, "post": post_v}
        if diffs:
            mismatches.append(
                {
                    "bar_index": int(row["bar_index"]),
                    "timestamp": str(row.get("timestamp_pre", row.get("timestamp_post", ""))),
                    "diffs": diffs,
                }
            )
    return {
        "bars_compared": int(len(merged)),
        "mismatch_bars": len(mismatches),
        "identical": len(mismatches) == 0,
        "mismatches": mismatches[:50],
    }


def main() -> int:
    m1, m5, m15 = load_markets_lw()
    report = {
        "method": "Phase72B mirror inline vs gate_snap_mode (NOT TradingView Pine)",
        "pine_action": "reverted_to_additive_only — inline if drives live branch; gldSnapGateOpen export-only",
        "windows": [],
    }

    for wid, start, end in WINDOWS:
        s_i, e_i = window_indices(m1, start, end)
        _, ev_pre, _, _ = run_mirror(m1, m5, m15, s_i, e_i, gate_snap_mode=False)
        _, ev_post, _, _ = run_mirror(m1, m5, m15, s_i, e_i, gate_snap_mode=True)
        pre_df = events_to_dataframe(ev_pre)[["bar_index", "timestamp", *SIGNAL_COLS]]
        post_df = events_to_dataframe(ev_post)[["bar_index", "timestamp", *SIGNAL_COLS]]
        cmp = _compare(pre_df, post_df)
        cmp["window_id"] = wid
        cmp["start"] = start
        cmp["end"] = end
        cmp["pre_counts"] = {c: int(pre_df[c].sum()) for c in SIGNAL_COLS}
        cmp["post_counts"] = {c: int(post_df[c].sum()) for c in SIGNAL_COLS}
        report["windows"].append(cmp)

    report["all_windows_identical"] = all(w["identical"] for w in report["windows"])
    report["conclusion"] = (
        "Mirror proxy: inline and same-bar gate_snap are bar-for-bar identical on signal_long/short/enter_long/enter_short."
        if report["all_windows_identical"]
        else "Mirror proxy: divergence detected — additive-only revert applied in Pine."
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(
        json.dumps(
            {w["window_id"]: {"identical": w["identical"], "mismatch_bars": w["mismatch_bars"]} for w in report["windows"]},
            indent=2,
        )
    )
    print(f"all_identical={report['all_windows_identical']}")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
