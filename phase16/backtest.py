"""Orchestration for the frozen causal CRT backtest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from .config import FrozenConfig
from .entry_models import EntryFunnel
from .indicators import (
    add_base_indicators,
    add_previous_closed_htf_regime,
    crt_reference_and_sweeps,
)
from .liquidity import LiquidityEngine
from .models import MODELS
from .setup_engine import SetupEngine
from .structure import StructureEngine
from .trade_engine import TradeEngine


TRADE_COLUMNS = [
    "model",
    "direction",
    "setup_timestamp",
    "bos_timestamp",
    "retest_timestamp",
    "confirm_timestamp",
    "entry_timestamp",
    "exit_timestamp",
    "entry_price",
    "stop_price",
    "target_price",
    "exit_price",
    "result_R",
    "score",
    "htf_regime",
    "session_bucket",
    "exit_reason",
]


@dataclass
class BacktestResult:
    trades: pd.DataFrame
    events: pd.DataFrame
    diagnostics: Dict[str, object]
    coverage: str
    start_timestamp: pd.Timestamp
    end_exclusive: pd.Timestamp


def validation_window(
    start: str, end: str, exchange_timezone: str
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts.tzinfo is None:
        start_ts = start_ts.tz_localize(exchange_timezone)
    else:
        start_ts = start_ts.tz_convert(exchange_timezone)
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize(exchange_timezone)
    else:
        end_ts = end_ts.tz_convert(exchange_timezone)
    end_exclusive = (end_ts.normalize() + pd.DateOffset(days=1)).tz_convert(
        exchange_timezone
    )
    start_ts = start_ts.normalize()
    if end_exclusive <= start_ts:
        raise ValueError("end date must be on or after start date")
    return start_ts, end_exclusive


def _empty_trades() -> pd.DataFrame:
    return pd.DataFrame(columns=TRADE_COLUMNS)


def run_backtest(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig = FrozenConfig(),
    debug_events: bool = False,
) -> BacktestResult:
    """Run all four Phase 14 models on a date-scoped window.

    The entire supplied history is processed before ``start`` to warm causal
    state, but entries/funnel advancement are allowed only inside the inclusive
    date window. This mirrors Pine's chart-history execution and Phase 14 gate.
    """
    if frame.empty:
        raise ValueError("market data is empty")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise TypeError("market data must use a timezone-aware DatetimeIndex")
    if not frame.index.is_monotonic_increasing:
        frame = frame.sort_index()
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    data = frame.tz_convert(config.exchange_timezone).copy()
    data = add_base_indicators(data, config)
    data = add_previous_closed_htf_regime(data, config)
    crt = crt_reference_and_sweeps(data)
    data = data.join(crt)

    first_bar = data.index[0]
    last_bar_end = data.index[-1] + pd.Timedelta(config.chart_minutes, unit="m")
    coverage = (
        "FULL DATA"
        if first_bar <= start_ts and last_bar_end >= end_exclusive
        else "PARTIAL DATA"
    )

    structure_engine = StructureEngine(config)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    funnel = EntryFunnel(config)
    trades = TradeEngine(config)

    bars_in_window = 0
    raw_long = 0
    raw_short = 0
    canonical = 0
    event_rows = []
    previous_close: Optional[float] = None
    previous_timestamp: Optional[pd.Timestamp] = None
    last_processed_close: Optional[float] = None
    last_processed_timestamp: Optional[pd.Timestamp] = None

    for bar_index, row in enumerate(data.itertuples()):
        timestamp = row.Index
        structure_event = structure_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.structure_pivot_high),
            pivot_low=float(row.structure_pivot_low),
        )
        liquidity_event = liquidity_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.liquidity_pivot_high),
            pivot_low=float(row.liquidity_pivot_low),
        )
        setup_event = setup_engine.step(
            bar_index=bar_index,
            timestamp=timestamp,
            open_price=float(row.open),
            close=float(row.close),
            atr=float(row.atr),
            body_average=float(row.body_sma),
            htf_regime=int(row.htf_regime),
            structure=structure_event,
            liquidity=liquidity_event,
        )

        in_window = start_ts <= timestamp < end_exclusive
        if in_window:
            bars_in_window += 1
            raw_long += int(setup_event.long_setup)
            raw_short += int(setup_event.short_setup)
            canonical += int(setup_event.canonical)
            entry_events = funnel.step(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=float(row.atr),
                setup=setup_event,
                structure=structure_event,
            )
            for entry in entry_events:
                trades.try_open(
                    entry,
                    bar_index=bar_index,
                    close=float(row.close),
                    atr=float(row.atr),
                )
            if debug_events:
                event_rows.append(
                    {
                        "timestamp": timestamp,
                        "bull_BOS": structure_event.bull_bos,
                        "bear_BOS": structure_event.bear_bos,
                        "liquidity_sweep": liquidity_event.any_sweep,
                        "long_setup": setup_event.long_setup,
                        "short_setup": setup_event.short_setup,
                        "canonical_long": setup_event.canonical_long,
                        "canonical_short": setup_event.canonical_short,
                        "funnel_state": funnel.state_name,
                    }
                )

        bar_end = timestamp + pd.Timedelta(config.chart_minutes, unit="m")
        trades.manage_bar(
            bar_index=bar_index,
            timestamp=timestamp,
            bar_end=bar_end,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            end_exclusive=end_exclusive,
            previous_close=previous_close,
            previous_timestamp=previous_timestamp,
        )
        previous_close = float(row.close)
        previous_timestamp = timestamp
        last_processed_close = float(row.close)
        last_processed_timestamp = timestamp

        # Nothing after the first out-of-window bar can affect this run.
        if timestamp >= end_exclusive and not trades.active:
            break

    if trades.active and last_processed_close is not None and last_processed_timestamp is not None:
        trades.close_remaining(
            timestamp=last_processed_timestamp,
            close=last_processed_close,
            reason="DATA_END" if coverage == "PARTIAL DATA" else "WINDOW_END",
        )

    trade_frame = (
        pd.DataFrame([trade.export_dict() for trade in trades.completed])
        if trades.completed
        else _empty_trades()
    )
    if not trade_frame.empty:
        trade_frame = trade_frame[TRADE_COLUMNS].sort_values(
            ["exit_timestamp", "model"], kind="stable"
        ).reset_index(drop=True)
    events = pd.DataFrame(event_rows)
    diagnostics: Dict[str, object] = {
        "Bars In Window": bars_in_window,
        "Raw Long Setups": raw_long,
        "Raw Short Setups": raw_short,
        "Raw Setup Total": raw_long + raw_short,
        "Canonical Raw Setups": canonical,
        "Control Attempts": trades.attempts["Control"],
        "Control Accepted": trades.accepted["Control"],
        "BOS Attempts": trades.attempts["BOS"],
        "BOS Accepted": trades.accepted["BOS"],
        "Retest Attempts": trades.attempts["Retest"],
        "Retest Accepted": trades.accepted["Retest"],
        "Confirm Attempts": trades.attempts["Confirm"],
        "Confirm Accepted": trades.accepted["Confirm"],
        "First Loaded Bar": first_bar,
        "Last Loaded Bar End": last_bar_end,
        "Start Timestamp": start_ts,
        "End Exclusive": end_exclusive,
    }
    return BacktestResult(
        trades=trade_frame,
        events=events,
        diagnostics=diagnostics,
        coverage=coverage,
        start_timestamp=start_ts,
        end_exclusive=end_exclusive,
    )
