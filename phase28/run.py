#!/usr/bin/env python3
"""Run Phase 28 multi-timeframe strategy comparison."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from phase16.config import FrozenConfig
from phase16.data_loader import load_ohlcv_csv
from phase28.analyze import run_phase28, summarize_trades
from phase28.config import (
    COMMON_END,
    COMMON_START,
    NQ_5M_PATHS,
    PARITY_WINDOWS,
    RESULTS,
    STRATEGIES_EXCLUDED,
    STRATEGIES_INCLUDED,
)
from phase28.resample_timeframes import aggregate_from_5m
from phase28.strategies import collect_strategy_trades


def load_base_5m() -> pd.DataFrame:
    tz = FrozenConfig().exchange_timezone
    frames = [load_ohlcv_csv(p, exchange_timezone=tz) for p in NQ_5M_PATHS]
    market = pd.concat(frames).sort_index()
    return market[~market.index.duplicated(keep="last")]


def verify_parity(base5: pd.DataFrame) -> None:
    config = replace(FrozenConfig(), chart_minutes=5)
    failures = []
    for label, model, start, end, expected, tol in PARITY_WINDOWS:
        runs = collect_strategy_trades(base5, start=start, end=end, config=config)
        if label == "CRT_V2":
            actual = len(runs["CRT_V2_B_LEGACY_EXP6"].trades)
        elif label == "RETEST_GATED":
            actual = len(runs["RETEST_GATED"].trades)
        elif label == "BOS_ONLY":
            actual = len(runs["BOS_ONLY"].trades)
        else:
            actual = len(runs[label].trades) if label in runs else 0
        if abs(actual - expected) > tol:
            failures.append(f"{label}: expected N≈{expected}, got {actual} (tol={tol})")
    if failures:
        raise RuntimeError("5m parity failed:\n" + "\n".join(failures))


def write_audit_docs(output: Path) -> None:
    (output / "timeframe_data_audit.md").write_text(
        "# Timeframe data audit\n\n"
        f"- Source: stitched local NQ **5m** OHLCV ({len(NQ_5M_PATHS)} files)\n"
        f"- Common comparison range: **{COMMON_START} → {COMMON_END}**\n"
        f"- Higher TFs built by causal aggregation from 5m (session-aware, no lookahead)\n"
        f"- No new Databento purchases\n\n"
        "## Strategies included\n"
        + "\n".join(f"- {s}" for s in STRATEGIES_INCLUDED)
        + "\n\n## Strategies excluded\n"
        + "\n".join(f"- {s}" for s in STRATEGIES_EXCLUDED)
        + "\n"
    )
    (output / "timeframe_parameter_mapping.md").write_text(
        "# Parameter mapping across timeframes\n\n"
        "## A. Price/volatility based (unchanged)\n"
        "- `trade_stop_atr=1.5`, `trade_target_r=2.0`, `p12_retest_atr_tolerance=0.10`\n"
        "- ATR length = 14 bars on each timeframe\n\n"
        "## B. Time-based (elapsed minutes preserved)\n"
        "- `trade_max_minutes=60` → bars = 60/chart_minutes\n"
        "  - 5m=12, 15m=4, 30m=2, 60m=1\n"
        "- HTF regime remains **60-minute** wall clock\n\n"
        "## C. Structural bar-count (unchanged)\n"
        "- Pivots 5/5, `p12_expiry_bars=8`, `se_cooldown_bars=5`, sequential expiry=3, CRT V2 expiry=6\n"
        "- These represent **different elapsed time** on higher TFs (documented, not rescaled)\n"
    )


def main() -> int:
    output = RESULTS
    output.mkdir(parents=True, exist_ok=True)
    write_audit_docs(output)
    base5 = load_base_5m()
    print("Verifying 5m parity windows...", flush=True)
    verify_parity(base5)
    print("Parity OK.", flush=True)
    manifest = run_phase28(output=output)
    (output / "MULTI_TIMEFRAME_STRATEGY_REPORT.md").write_text(
        "# Multi-Timeframe Strategy Report\n\n"
        f"Best combination: **{manifest['best_overall_strategy']} @ {manifest['best_overall_timeframe']}m**\n\n"
        f"See strategy_timeframe_summary.csv and research_manifest.json\n"
    )
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
