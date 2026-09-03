"""Run frozen strategy architectures on a timeframe-specific market frame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd

from phase16.backtest import run_backtest
from phase16.config import FrozenConfig
from phase16.crt_setup_v2 import (
    SetupV2Archetype,
    SetupV2Qualification,
    SetupV2Variant,
    run_setup_v2_backtest,
)
from phase16.sequential_bos import (
    BosDefinition,
    FunnelCounters,
    SequentialBosConfig,
    run_sequential_bos_backtest,
)


@dataclass
class StrategyRun:
    trades: pd.DataFrame
    diagnostics: Dict[str, object]
    funnel: Optional[object] = None


def run_frozen_backtest(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig,
) -> StrategyRun:
    result = run_backtest(frame, start=start, end=end, config=config)
    return StrategyRun(trades=result.trades, diagnostics=result.diagnostics)


def run_sequential_bos(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig,
) -> StrategyRun:
    seq = SequentialBosConfig(
        bos_definition=BosDefinition.SWING_2_2,
        setup_bos_expiry_bars=3,
    )
    result, counters = run_sequential_bos_backtest(
        frame, start=start, end=end, config=config, seq_config=seq
    )
    return StrategyRun(trades=result.trades, diagnostics=result.diagnostics, funnel=counters)


def run_crt_v2(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig,
) -> StrategyRun:
    variant = SetupV2Variant(
        SetupV2Archetype.NEXT_BAR,
        SetupV2Qualification.LEGACY_QUALIFIED,
        6,
    )
    trades, counters, *_ = run_setup_v2_backtest(
        frame, variant=variant, start=start, end=end, config=config
    )
    return StrategyRun(trades=trades, diagnostics={}, funnel=counters)


def collect_strategy_trades(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig,
) -> Dict[str, StrategyRun]:
    base = run_frozen_backtest(frame, start=start, end=end, config=config)
    out = {
        "CONTROL": StrategyRun(
            trades=base.trades.loc[base.trades["model"] == "Control"].copy(),
            diagnostics=base.diagnostics,
        ),
        "RETEST_GATED": StrategyRun(
            trades=base.trades.loc[base.trades["model"] == "Confirm"].copy(),
            diagnostics=base.diagnostics,
        ),
        "BOS_ONLY": StrategyRun(
            trades=base.trades.loc[base.trades["model"] == "BOS"].copy(),
            diagnostics=base.diagnostics,
        ),
        "SEQUENTIAL_BOS": run_sequential_bos(frame, start=start, end=end, config=config),
        "CRT_V2_B_LEGACY_EXP6": run_crt_v2(frame, start=start, end=end, config=config),
    }
    return out
