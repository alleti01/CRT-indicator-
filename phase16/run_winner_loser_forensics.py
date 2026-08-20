#!/usr/bin/env python3
"""Run the development-only 42-trade winner/loser forensic analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase16.continuous import forward_adjust_rolls, select_provider_rolls
from phase16.data_loader import load_ohlcv_csv
from phase16.resample import resample_ohlcv
from phase16.winner_loser_forensics import run_forensics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="phase16/data/nq_continuous_1m_raw.csv")
    parser.add_argument("--start", default="2026-06-29")
    parser.add_argument("--end", default="2026-08-18")
    parser.add_argument("--current-trades", default="phase16/results/retest_reclaim_research/current_confirm_trades.csv")
    parser.add_argument("--candidates", default="phase16/results/retest_gate_forensics/all_setup_candidates.csv")
    parser.add_argument("--output", default="phase16/results/winner_loser_entry_quality")
    args = parser.parse_args()

    config = FrozenConfig()
    data = load_ohlcv_csv(args.data, exchange_timezone=config.exchange_timezone)
    data = forward_adjust_rolls(select_provider_rolls(data))
    # Incomplete groups are retained because this is the parity-validated
    # TradingView construction used to produce the frozen 42-trade baseline.
    data = resample_ohlcv(data, config.chart_minutes, require_complete=False)
    project_root = Path(__file__).resolve().parent.parent
    result = run_forensics(
        data,
        current_trade_path=Path(args.current_trades),
        candidate_path=Path(args.candidates),
        output=Path(args.output),
        start=args.start,
        end=args.end,
        config=config,
        project_root=project_root,
    )
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

