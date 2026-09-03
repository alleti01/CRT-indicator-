#!/usr/bin/env python3
"""Run CRT signal-edge localization / forward-return diagnostic study."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phase16.config import FrozenConfig
from phase16.crt_signal_edge_localization import run_signal_edge_study
from phase16.data_loader import load_ohlcv_csv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-cached-events", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    config = FrozenConfig()
    dev = load_ohlcv_csv(root / "phase16/data/processed/nq_5m.csv", exchange_timezone=config.exchange_timezone)
    observed = load_ohlcv_csv(
        root / "phase16/data/processed/nq_5m_oos_20171001_20201201.csv",
        exchange_timezone=config.exchange_timezone,
    )
    manifest = run_signal_edge_study(
        dev,
        observed,
        output=root / "phase16/results/crt_signal_edge_localization",
        config=config,
        use_cached_events=args.from_cached_events,
    )
    print(json.dumps(manifest, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
