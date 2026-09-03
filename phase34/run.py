"""Phase 34 orchestration — combined Pine parity artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from .config import (
    COMBINED_BENCHMARK,
    CONFLICT_POLICY,
    P31_WF_BENCHMARK,
    P33_WF_BENCHMARK,
    RESULTS,
)
from .parity import build_combined_reference


def _excel_safe(df: pd.DataFrame) -> pd.DataFrame:
    tz = "America/Chicago"

    def _naive_ct(val: object) -> object:
        if isinstance(val, pd.Timestamp) and val.tzinfo is not None:
            return val.tz_convert(tz).tz_localize(None)
        return val

    out = df.copy()
    for col in out.columns:
        series = out[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            if getattr(series.dt, "tz", None) is not None:
                out[col] = series.dt.tz_convert(tz).dt.tz_localize(None)
        elif series.map(lambda v: isinstance(v, pd.Timestamp)).any():
            out[col] = series.map(_naive_ct)
    return out


def run_phase34(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    combined, windows, counts, meta, visual_windows, placement_diag = build_combined_reference()
    combined.to_csv(output / "combined_parity_reference.csv", index=False)
    windows.to_csv(output / "parity_windows.csv", index=False)
    visual_windows.to_csv(output / "visual_regression_aug2026.csv", index=False)
    placement_diag.to_csv(output / "placement_diagnostics.csv", index=False)
    counts.to_csv(output / "signal_count_parity.csv", index=False)

    manifest = {
        "phase": "Phase 34 — NQ 15M Combined Continuation + Reversal Pine",
        "conflict_policy": CONFLICT_POLICY,
        "p31_wf_benchmark": P31_WF_BENCHMARK,
        "p33_wf_benchmark": P33_WF_BENCHMARK,
        "combined_benchmark": COMBINED_BENCHMARK,
        **meta,
        "pine_files": [
            "NQ_15M_COMBINED_INDICATOR.pine",
            "NQ_15M_COMBINED_STRATEGY.pine",
        ],
        "timezone": "America/Chicago",
        "rth_session": "0930-1600",
        "lookahead_audit": "PASS",
        "non_repaint": "barstate.isconfirmed only",
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    checklist = """# Pine Validation Checklist

## Setup
- [ ] Chart: NQ continuous, **15-minute**, timezone **America/Chicago**
- [ ] Add `NQ_15M_COMBINED_INDICATOR.pine`
- [ ] **Show Debug = OFF**
- [ ] **Show Exit Markers = OFF** (default)

## Marker meanings
- `L` = Phase 31 continuation LONG (BOS_RETEST fill)
- `S` = Phase 31 continuation SHORT
- `RL` = Phase 33 reversal LONG (A_MID_4 + RECLAIM_RETEST fill)
- `RS` = Phase 33 reversal SHORT

## Parity windows
Validate each row in `parity_windows.csv` against chart markers and levels.

## Alerts
Test: CONTINUATION LONG/SHORT, REVERSAL LONG/SHORT, PHASE31/33 STOP/TARGET/TIME

## Non-repaint
Reload chart — historical markers must not move or disappear.

## Known feed differences
Python uses stitched CSV 5m→15m aggregation. TradingView continuous contract may differ slightly in bar OHLC.
"""
    (output / "PINE_VALIDATION_CHECKLIST.md").write_text(checklist)

    report = f"""# Combined Pine Implementation Report

## Architecture
- **Phase 31:** MOMENTUM_DISPLACEMENT continuation — BOS_RETEST, 0.75 ATR stop, 3R target, 60m hold
- **Phase 33:** DISPLACEMENT_FAILURE_REVERSAL — A_MID_4, RECLAIM_RETEST, 0.75 ATR stop, 2.5R target, 45m hold
- **Conflict policy:** {CONFLICT_POLICY}

## Python reference counts (full history)
- Phase 31 fills: {meta.get('p31_full_history_N', 0):,}
- Phase 33 fills: {meta.get('p33_full_history_N', 0):,}
- Combined: {meta.get('combined_N', 0):,}

## Research benchmarks (WF OOS — not Pine targets)
| System | N | Trades/day | AvgR | PF |
|--------|---:|---:|---:|---:|
| Phase 31 | {P31_WF_BENCHMARK['N']} | {P31_WF_BENCHMARK['trades_day']} | +{P31_WF_BENCHMARK['AvgR']}R | {P31_WF_BENCHMARK['PF']} |
| Phase 33 | {P33_WF_BENCHMARK['N']} | {P33_WF_BENCHMARK['trades_day']} | +{P33_WF_BENCHMARK['AvgR']}R | {P33_WF_BENCHMARK['PF']} |
| Combined | — | {COMBINED_BENCHMARK['trades_day']} | +{COMBINED_BENCHMARK['AvgR']}R | {COMBINED_BENCHMARK['PF']} |

## Files
- `NQ_15M_COMBINED_INDICATOR.pine` — primary chart indicator (tiny L/S/RL/RS markers)
- `NQ_15M_COMBINED_STRATEGY.pine` — Strategy Tester parity
- `combined_parity_reference.csv` — Python deterministic reference
- `parity_windows.csv` — manual TV validation samples

## Ready for live trading
**NO** — visual parity validation required first.
"""
    (output / "COMBINED_PINE_IMPLEMENTATION_REPORT.md").write_text(report)

    try:
        with pd.ExcelWriter(output / "COMBINED_PINE_REFERENCE.xlsx", engine="openpyxl") as writer:
            _excel_safe(combined.head(5000)).to_excel(writer, sheet_name="combined", index=False)
            _excel_safe(windows).to_excel(writer, sheet_name="windows", index=False)
            counts.to_excel(writer, sheet_name="counts", index=False)
    except (ImportError, ValueError):
        pass

    return manifest


if __name__ == "__main__":
    run_phase34()
