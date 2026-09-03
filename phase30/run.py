#!/usr/bin/env python3
"""Phase 30 — Pine implementation parity export and manifest."""

from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase30.config import (
    AMBIGUOUS_BAR_POLICY,
    BASELINE_15M,
    ENTRY_MODEL,
    MANAGEMENT,
    MAX_HOLD_MINUTES,
    RESULTS,
    SIGNAL_ARCHITECTURE,
    STOP_ATR,
    TARGET_R,
    WF_EXECUTION,
)
from phase30.parity import build_parity_reference


def main() -> None:
    out = RESULTS
    out.mkdir(parents=True, exist_ok=True)
    tests_dir = Path(__file__).resolve().parent / "tests"
    tests_dir.mkdir(exist_ok=True)

    reference, windows, perf = build_parity_reference()
    reference.to_csv(out / "pine_parity_reference.csv", index=False)
    windows.to_csv(out / "parity_windows.csv", index=False)

    manifest = {
        "phase": 30,
        "signal_architecture": SIGNAL_ARCHITECTURE,
        "timeframe_minutes": 15,
        "entry_model": ENTRY_MODEL,
        "stop_atr": STOP_ATR,
        "target_r": TARGET_R,
        "max_hold_minutes": MAX_HOLD_MINUTES,
        "management": MANAGEMENT,
        "ambiguous_bar_policy": AMBIGUOUS_BAR_POLICY,
        "baseline_15m_signal": BASELINE_15M,
        "phase29_walk_forward_execution": WF_EXECUTION,
        "python_parity_filled_trades": int(perf.get("N", 0)),
        "python_parity_net_avg_r": round(float(perf.get("net_AvgR", float("nan"))), 4),
        "python_parity_net_total_r": round(float(perf.get("net_TotalR", float("nan"))), 2),
        "ready_for_tradingview_visual_validation": True,
        "live_deployment_validated": False,
        "outputs": {
            "strategy_pine": str(out / "CRT_V2_15M_FINAL_STRATEGY.pine"),
            "indicator_pine": str(out / "CRT_V2_15M_FINAL_INDICATOR.pine"),
            "parity_reference_csv": str(out / "pine_parity_reference.csv"),
            "parity_windows_csv": str(out / "parity_windows.csv"),
            "report_md": str(out / "PINE_IMPLEMENTATION_REPORT.md"),
        },
    }
    (out / "study_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
