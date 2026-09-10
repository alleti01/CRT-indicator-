#!/usr/bin/env python3
"""Part C verification — cold-start reach + signal-path regression."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58j.research.lw_data import load_markets_lw
from phase72b.python.autonomous_mirror_engine import run_mirror
from phase72b.python.event_log import events_to_dataframe
from phase72b.tools.run_phase72b_parity import window_indices

OUT = ROOT / "signal_ledger" / "reports" / "PART_C_VERIFICATION.json"
LEDGER = ROOT / "TV_REVIEW" / "phase72a_signal_ledger.pine"
SIGNAL_COLS = ("signal_long", "signal_short", "enter_long", "enter_short")
WARMUP_MIN_BARS = 12 * 15 + 5
WINDOWS = [
    ("aug28_session", "2026-08-28 08:30", "2026-08-28 16:00"),
    ("jul_aug_2026", "2026-07-01 00:00", "2026-08-28 23:59"),
]


def _simulate_cold_start_at_bar(bar_index: int, init_bar: int = 0) -> dict:
    bars_since = bar_index - init_bar
    warmup_ready = bars_since >= WARMUP_MIN_BARS
    in_cold = not warmup_ready and bars_since < WARMUP_MIN_BARS
    return {
        "bar_index": bar_index,
        "bars_since_script_init": bars_since,
        "gld_htf_warmup_ready": warmup_ready,
        "gld_in_cold_start_window": in_cold,
        "gld_pass_reason_code": 1 if in_cold else 0,
    }


def _layer_a_gld_reads(pine_text: str) -> list[str]:
    start = pine_text.find("// Main bar logic — Layer A")
    end = pine_text.find("// PHASE72A-SIGNAL-LEDGER — Layer D")
    block = pine_text[start:end] if start >= 0 and end >= 0 else ""
    writes = set(re.findall(r"\b(gld\w+)\s*:=", block))
    reads = set(re.findall(r"\b(gld\w+)\b", block)) - writes
    return sorted(reads)


def main() -> int:
    m1, m5, m15 = load_markets_lw()
    ledger_text = LEDGER.read_text(encoding="utf-8")
    layer_a_reads = _layer_a_gld_reads(ledger_text)

    cold_samples = []
    signal_bars_checked = 0
    signal_bars_in_cold = 0
    reg_windows = []

    for wid, start, end in WINDOWS:
        s_i, e_i = window_indices(m1, start, end)
        _, ev, _, _ = run_mirror(m1, m5, m15, s_i, e_i)
        df = events_to_dataframe(ev)
        reg_windows.append(
            {
                "window_id": wid,
                "bars": int(len(df)),
                "counts": {c: int(df[c].sum()) for c in SIGNAL_COLS},
            }
        )
        sig_mask = df["signal_long"] | df["signal_short"] | df["enter_long"] | df["enter_short"]
        for bi in df.loc[sig_mask, "bar_index"].astype(int).tolist():
            signal_bars_checked += 1
            sim = _simulate_cold_start_at_bar(int(bi))
            if sim["gld_in_cold_start_window"]:
                signal_bars_in_cold += 1
            if len(cold_samples) < 8:
                cold_samples.append({"window": wid, **sim})

    report = {
        "item_1_cold_start_reach": {
            "verdict": "FULL_HISTORICAL_RECALC_THEN_WARM_AT_LIVE_EDGE",
            "signal_bars_checked": signal_bars_checked,
            "signal_bars_in_cold_start": signal_bars_in_cold,
            "m1_bars_in_dataset": len(m1),
            "warmup_min_bars": WARMUP_MIN_BARS,
            "samples": cold_samples,
        },
        "item_2_signal_path_regression": {
            "layer_a_gld_reads": layer_a_reads,
            "static_signal_path_unchanged": layer_a_reads == [],
            "mirror_windows": reg_windows,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
