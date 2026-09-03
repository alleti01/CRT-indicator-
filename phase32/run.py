"""Generate Phase 32 Pine parity artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .config import (
    AMBIGUOUS_BAR_POLICY,
    BODY_AVG_LOOKBACK,
    BODY_MULTIPLIER,
    CLOSE_LOC_LONG_MIN,
    CLOSE_LOC_SHORT_MAX,
    COMMON_END,
    COMMON_START,
    DEDUPE_ACTIVE_BARS,
    ENTRY_MODEL,
    MANAGEMENT,
    MAX_HOLD_BARS,
    MAX_HOLD_MINUTES,
    MAX_SIGNALS_PER_RTH_DAY,
    MIN_BARS_BETWEEN_SAME_DIR,
    PHASE31_STITCHED_WF,
    RESULTS,
    RTH_SESSION,
    SIGNAL_ARCHITECTURE,
    STOP_ATR,
    TARGET_R,
    TIMEFRAME_MINUTES,
)
from .parity import build_parity_reference


def run_phase32(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    reference, windows, meta = build_parity_reference(start=COMMON_START, end=COMMON_END)
    reference.to_csv(output / "pine_parity_reference.csv", index=False)
    windows.to_csv(output / "parity_windows.csv", index=False)

    dry = meta.get("dry_stretch_audit", {})
    report = _build_report(reference, meta, dry)
    (output / "PINE_IMPLEMENTATION_REPORT.md").write_text(report)

    manifest = {
        "phase": "Phase 32 — NQ 15M Momentum Displacement Pine Implementation",
        "architecture": SIGNAL_ARCHITECTURE,
        "timeframe_minutes": TIMEFRAME_MINUTES,
        "frozen_execution": {
            "entry_model": ENTRY_MODEL,
            "stop_atr": STOP_ATR,
            "target_r": TARGET_R,
            "max_hold_minutes": MAX_HOLD_MINUTES,
            "max_hold_bars": MAX_HOLD_BARS,
            "management": MANAGEMENT,
        },
        "displacement": {
            "body_multiplier": BODY_MULTIPLIER,
            "body_avg_lookback": BODY_AVG_LOOKBACK,
            "close_loc_long_min": CLOSE_LOC_LONG_MIN,
            "close_loc_short_max": CLOSE_LOC_SHORT_MAX,
            "rth_session": RTH_SESSION,
        },
        "deduplication": {
            "one_active_trade": True,
            "active_bars": DEDUPE_ACTIVE_BARS,
            "min_bars_same_direction": MIN_BARS_BETWEEN_SAME_DIR,
            "max_signals_per_rth_day": MAX_SIGNALS_PER_RTH_DAY,
        },
        "ambiguous_bar_policy": AMBIGUOUS_BAR_POLICY,
        "phase31_stitched_wf_reference": PHASE31_STITCHED_WF,
        "full_frozen_parity": meta,
        "dry_stretch_audit": dry,
        "parity_trade_count": int(len(reference)),
        "strategy_pine": str(output / "MOMENTUM_DISPLACEMENT_15M_FINAL_STRATEGY.pine"),
        "indicator_pine": str(output / "MOMENTUM_DISPLACEMENT_15M_FINAL_INDICATOR.pine"),
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return manifest


def _build_report(reference, meta, dry) -> str:
    lines = [
        "# Phase 32 — Momentum Displacement Pine Implementation Report",
        "",
        "## Frozen Architecture",
        f"- Signal: **{SIGNAL_ARCHITECTURE}**",
        f"- Timeframe: **{TIMEFRAME_MINUTES}m**",
        f"- Displacement: body > {BODY_MULTIPLIER}× {BODY_AVG_LOOKBACK}-bar avg body; close in top/bottom 20%",
        f"- Entry: **{ENTRY_MODEL}** (phase29.simulator.resolve_entry literal)",
        f"- Stop: {STOP_ATR} ATR · Target: {TARGET_R}R · Hold: {MAX_HOLD_MINUTES}m ({MAX_HOLD_BARS} bars) · {MANAGEMENT}",
        "",
        "## BOS_RETEST Rules (from phase29.simulator)",
        "- BOS bar = displacement bar; `bos_level` = bar high (long) or bar low (short)",
        "- Tolerance = 0.10 × ATR(14) on displacement bar",
        "- Window = 2 bars strictly after displacement close",
        "- Long fill when `low <= bos_level + tol`; price = min(bos_level + tol, close)",
        "- Short fill when `high >= bos_level - tol`; price = max(bos_level - tol, close)",
        "- Stop ATR measured at entry bar; ambiguous bar: **STOP before TARGET**",
        "",
        "## Population Distinction",
        f"- **Stitched WF (Phase 31 headline):** N={PHASE31_STITCHED_WF['N']}, trades/day≈{PHASE31_STITCHED_WF['trades_per_day']}",
        f"- **Full frozen parity (this Pine reference):** N={meta.get('N', 0)}, Net AvgR={meta.get('AvgR', 0):.4f}R",
        "",
        "## Dry-Stretch Audit",
        f"- Phase 31 reported: **{dry.get('phase31_reported', '?')}** RTH days",
        f"- Correct (full frozen fills): **{dry.get('correct_full_frozen_longest_dry', '?')}** RTH days",
        f"- Correct (WF eligible 2020+): **{dry.get('correct_wf_period_longest_dry', '?')}** RTH days",
        f"- Cause: {dry.get('cause', '')}",
        "",
        "## TradingView Notes",
        "Python uses stitched local NQ 5m→15m data. TradingView NQ1! may differ on rolls,",
        "back-adjustment, and session boundaries. Logic parity first — do not retune to match TV data.",
        "",
        "## Files",
        "- MOMENTUM_DISPLACEMENT_15M_FINAL_STRATEGY.pine",
        "- MOMENTUM_DISPLACEMENT_15M_FINAL_INDICATOR.pine",
        "- pine_parity_reference.csv",
        "- parity_windows.csv",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    run_phase32()
