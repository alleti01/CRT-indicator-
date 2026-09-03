"""Experimental SEQUENTIAL_BOS entry architecture for Phase 16 research.

ORIGINAL and RETEST_GATED delegate to the frozen ``run_backtest`` path.
SEQUENTIAL_BOS enforces strict causal ordering:

    setup_bar < bos_bar < retest_bar < confirm_bar <= entry_bar

No same-bar Setup+BOS, BOS+Retest, or Retest+Confirm transitions are allowed.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional

import numpy as np
import pandas as pd

from .backtest import BacktestResult, TRADE_COLUMNS, run_backtest, validation_window
from .bos_semantic_audit import CausalSwingEngine, SwingBreak
from .config import FrozenConfig
from .entry_models import EntryFunnel
from .indicators import add_base_indicators, add_previous_closed_htf_regime, confirmed_pivots, crt_reference_and_sweeps
from .liquidity import LiquidityEngine
from .models import EntryEvent, SetupEvent, StructureEvent, Trade
from .setup_engine import SetupEngine
from .structure import StructureEngine
from .metrics import _drawdown
from .trade_archetype_decomposition import (
    NQ_DOLLARS_PER_POINT,
    ROUND_TURN_COST_USD,
    verify_archived_baseline,
)


def _profit_factor(values: pd.Series) -> float:
    gross_profit = float(values[values > 0].sum())
    gross_loss = float(-values[values < 0].sum())
    if gross_loss > 0:
        return gross_profit / gross_loss
    return 99.9 if gross_profit > 0 else 0.0


def _summarize_with_costs(trades: pd.DataFrame) -> Dict[str, float | int]:
    if trades.empty:
        return {
            "N": 0,
            "wins": 0,
            "losses": 0,
            "WR": 0.0,
            "gross_AvgR": 0.0,
            "net_AvgR": 0.0,
            "gross_TotalR": 0.0,
            "net_TotalR": 0.0,
            "gross_PF": 0.0,
            "net_PF": 0.0,
            "MaxDD": 0.0,
        }
    enriched = apply_costs(trades.sort_values("exit_timestamp"))
    gross = enriched.gross_R.astype(float)
    net = enriched.net_R.astype(float)
    return {
        "N": int(len(enriched)),
        "wins": int((net > 0).sum()),
        "losses": int((net < 0).sum()),
        "WR": float((net > 0).mean() * 100.0),
        "gross_AvgR": float(gross.mean()),
        "net_AvgR": float(net.mean()),
        "gross_TotalR": float(gross.sum()),
        "net_TotalR": float(net.sum()),
        "gross_PF": _profit_factor(gross),
        "net_PF": _profit_factor(net),
        "MaxDD": _drawdown(net),
    }
from .trade_engine import TradeEngine
from .trade_archetype_decomposition import verify_archived_baseline


ArchitectureMode = Literal["ORIGINAL", "RETEST_GATED", "SEQUENTIAL_BOS"]


class BosDefinition(str, Enum):
    NEXT_STRUCTURAL_EVENT = "NEXT_STRUCTURAL_EVENT"
    SWING_2_2 = "SWING_2_2"
    SWING_3_3 = "SWING_3_3"


SETUP_BOS_EXPIRY_OPTIONS = (3, 6, 12, 24)


@dataclass(frozen=True)
class SequentialBosConfig:
    bos_definition: BosDefinition = BosDefinition.NEXT_STRUCTURAL_EVENT
    setup_bos_expiry_bars: Optional[int] = 12
    debug_events: bool = False

    def __post_init__(self) -> None:
        if self.setup_bos_expiry_bars is not None and self.setup_bos_expiry_bars not in SETUP_BOS_EXPIRY_OPTIONS:
            raise ValueError(
                f"setup_bos_expiry_bars must be one of {SETUP_BOS_EXPIRY_OPTIONS} or None (OFF)"
            )


@dataclass
class FunnelCounters:
    qualified_setups: int = 0
    reached_bos: int = 0
    reached_retest: int = 0
    reached_confirmation: int = 0
    reached_entry: int = 0
    same_bar_setup_bos: int = 0
    same_bar_bos_retest: int = 0
    same_bar_retest_confirm: int = 0
    setup_to_bos_bars: List[int] = field(default_factory=list)
    bos_to_retest_bars: List[int] = field(default_factory=list)
    retest_to_confirm_bars: List[int] = field(default_factory=list)
    invalidations: Dict[str, int] = field(default_factory=dict)

    def record_invalidation(self, reason: str) -> None:
        self.invalidations[reason] = self.invalidations.get(reason, 0) + 1

    def export(self) -> Dict[str, Any]:
        return {
            "qualified_setups": self.qualified_setups,
            "reached_later_bos": self.reached_bos,
            "reached_retest": self.reached_retest,
            "reached_confirmation": self.reached_confirmation,
            "reached_entry": self.reached_entry,
            "same_bar_setup_bos": self.same_bar_setup_bos,
            "same_bar_bos_retest": self.same_bar_bos_retest,
            "same_bar_retest_confirm": self.same_bar_retest_confirm,
            "median_bars_setup_to_bos": _median(self.setup_to_bos_bars),
            "median_bars_bos_to_retest": _median(self.bos_to_retest_bars),
            "median_bars_retest_to_confirm": _median(self.retest_to_confirm_bars),
            "invalidations": dict(self.invalidations),
        }


def _median(values: List[int]) -> float:
    if not values:
        return float("nan")
    return float(np.median(values))


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def assert_strict_order(
    *,
    setup_bar: int,
    bos_bar: int,
    retest_bar: int,
    confirm_bar: int,
    entry_bar: int,
) -> None:
    if not (setup_bar < bos_bar < retest_bar < confirm_bar <= entry_bar):
        raise AssertionError(
            "SEQUENTIAL_BOS ordering violation: "
            f"setup={setup_bar}, bos={bos_bar}, retest={retest_bar}, "
            f"confirm={confirm_bar}, entry={entry_bar}"
        )
    if setup_bar == bos_bar or bos_bar == retest_bar or retest_bar == confirm_bar:
        raise AssertionError("SEQUENTIAL_BOS same-bar stage transition detected")


@dataclass
class SequentialBosFunnel:
    config: FrozenConfig
    seq_config: SequentialBosConfig
    state: int = 0
    direction: int = 0
    setup_bar: int = -1
    bos_bar: int = -1
    retest_bar: int = -1
    confirm_bar: int = -1
    score: float = 0.0
    bos_level: float = float("nan")
    bos_type: str = ""
    setup_timestamp: Optional[pd.Timestamp] = None
    bos_timestamp: Optional[pd.Timestamp] = None
    retest_timestamp: Optional[pd.Timestamp] = None
    confirm_timestamp: Optional[pd.Timestamp] = None
    htf_regime: int = 0
    session_bucket: int = 6
    last_invalidation: str = ""
    counters: FunnelCounters = field(default_factory=FunnelCounters)

    @property
    def state_name(self) -> str:
        return {0: "IDLE", 1: "WAIT_BOS", 2: "WAIT_RETEST", 3: "WAIT_CONFIRM"}.get(
            self.state, "IDLE"
        )

    def _reset(self, reason: str = "") -> None:
        if reason:
            self.last_invalidation = reason
            self.counters.record_invalidation(reason)
        self.state = 0
        self.direction = 0
        self.setup_bar = -1
        self.bos_bar = -1
        self.retest_bar = -1
        self.confirm_bar = -1
        self.score = 0.0
        self.bos_level = float("nan")
        self.bos_type = ""
        self.setup_timestamp = None
        self.bos_timestamp = None
        self.retest_timestamp = None
        self.confirm_timestamp = None

    def _setup_bos_expired(self, bar_index: int) -> bool:
        expiry = self.seq_config.setup_bos_expiry_bars
        if expiry is None:
            return False
        return self.setup_bar >= 0 and bar_index - self.setup_bar > expiry

    def _matching_bos_event(
        self,
        *,
        bar_index: int,
        structure: StructureEvent,
        swing_22: tuple[Optional[SwingBreak], Optional[SwingBreak]],
        swing_33: tuple[Optional[SwingBreak], Optional[SwingBreak]],
    ) -> tuple[bool, float, str]:
        if bar_index <= self.setup_bar:
            return False, float("nan"), ""

        definition = self.seq_config.bos_definition
        if definition == BosDefinition.NEXT_STRUCTURAL_EVENT:
            if self.direction == 1 and structure.bull_bos:
                prior = structure.previous_active_high
                current = structure.active_high
                level = prior if _finite(prior) else current
                return True, float(level), definition.value
            if self.direction == -1 and structure.bear_bos:
                prior = structure.previous_active_low
                current = structure.active_low
                level = prior if _finite(prior) else current
                return True, float(level), definition.value
            return False, float("nan"), ""

        engine_key = (2, 2) if definition == BosDefinition.SWING_2_2 else (3, 3)
        bull, bear = swing_22 if engine_key == (2, 2) else swing_33
        event = bull if self.direction == 1 else bear
        if event is None:
            return False, float("nan"), ""
        return True, float(event.level), definition.value

    def _opposite_bos(self, structure: StructureEvent) -> bool:
        return (self.direction == 1 and structure.bear_bos) or (
            self.direction == -1 and structure.bull_bos
        )

    def step(
        self,
        *,
        bar_index: int,
        timestamp: pd.Timestamp,
        open_price: float,
        high: float,
        low: float,
        close: float,
        atr: float,
        setup: SetupEvent,
        structure: StructureEvent,
        swing_22: tuple[Optional[SwingBreak], Optional[SwingBreak]],
        swing_33: tuple[Optional[SwingBreak], Optional[SwingBreak]],
    ) -> List[EntryEvent]:
        entries: List[EntryEvent] = []

        if setup.canonical and self.state == 0:
            self.state = 1
            self.direction = setup.canonical_direction
            self.setup_bar = bar_index
            self.bos_bar = -1
            self.retest_bar = -1
            self.confirm_bar = -1
            self.score = setup.canonical_score
            self.bos_level = float("nan")
            self.bos_type = ""
            self.setup_timestamp = timestamp
            self.bos_timestamp = None
            self.retest_timestamp = None
            self.confirm_timestamp = None
            self.htf_regime = setup.htf_regime
            self.session_bucket = setup.session_bucket
            self.counters.qualified_setups += 1

        if self.state == 1:
            same_bar_attempt = (self.direction == 1 and structure.bull_bos) or (
                self.direction == -1 and structure.bear_bos
            )
            if bar_index == self.setup_bar and same_bar_attempt:
                self.counters.same_bar_setup_bos += 1
                self._reset("same_bar_setup_bos")
                return entries
            bos_ok, level, bos_type = self._matching_bos_event(
                bar_index=bar_index,
                structure=structure,
                swing_22=swing_22,
                swing_33=swing_33,
            )
            if bos_ok:
                if bar_index <= self.setup_bar:
                    self.counters.same_bar_setup_bos += 1
                    self._reset("same_bar_setup_bos")
                    return entries
                self.bos_level = level
                self.bos_bar = bar_index
                self.bos_timestamp = timestamp
                self.bos_type = bos_type
                self.counters.reached_bos += 1
                self.counters.setup_to_bos_bars.append(bar_index - self.setup_bar)
                self.state = 2
            elif self._opposite_bos(structure):
                self._reset("opposite_bos_before_retest")
            elif self._setup_bos_expired(bar_index):
                self._reset("setup_bos_expiry")

        elif self.state == 2 and _finite(self.bos_level):
            tolerance = (atr if _finite(float(atr)) else 1.0) * self.config.p12_retest_atr_tolerance
            eligible = self.bos_bar >= 0 and bar_index > self.bos_bar
            would_touch = (
                low <= self.bos_level + tolerance
                if self.direction == 1
                else high >= self.bos_level - tolerance
            )
            if not eligible and would_touch:
                self.counters.same_bar_bos_retest += 1
                self._reset("same_bar_bos_retest")
                return entries
            touched = eligible and would_touch
            invalid = eligible and (
                close < self.bos_level - tolerance
                if self.direction == 1
                else close > self.bos_level + tolerance
            )
            if invalid:
                self._reset("retest_structure_failed")
            elif touched:
                self.retest_bar = bar_index
                self.retest_timestamp = timestamp
                self.counters.reached_retest += 1
                self.counters.bos_to_retest_bars.append(bar_index - self.bos_bar)
                self.state = 3
            elif self.bos_bar >= 0 and bar_index - self.bos_bar > self.config.p12_expiry_bars:
                self._reset("bos_retest_expiry")

        elif self.state == 3 and _finite(self.bos_level) and self.retest_bar >= 0:
            tolerance = (atr if _finite(float(atr)) else 1.0) * self.config.p12_retest_atr_tolerance
            eligible = bar_index > self.retest_bar
            would_confirm = (close > open_price and close > self.bos_level) if self.direction == 1 else (
                close < open_price and close < self.bos_level
            )
            if not eligible and would_confirm:
                self.counters.same_bar_retest_confirm += 1
                self._reset("same_bar_retest_confirm")
                return entries
            confirmed = eligible and would_confirm
            invalid = eligible and (
                close < self.bos_level - tolerance
                if self.direction == 1
                else close > self.bos_level + tolerance
            )
            if confirmed:
                self.confirm_bar = bar_index
                self.confirm_timestamp = timestamp
                self.counters.reached_confirmation += 1
                self.counters.retest_to_confirm_bars.append(bar_index - self.retest_bar)
                assert self.setup_timestamp is not None
                assert self.bos_timestamp is not None
                assert self.retest_timestamp is not None
                assert_strict_order(
                    setup_bar=self.setup_bar,
                    bos_bar=self.bos_bar,
                    retest_bar=self.retest_bar,
                    confirm_bar=self.confirm_bar,
                    entry_bar=bar_index,
                )
                if self.bos_timestamp <= self.setup_timestamp:
                    raise AssertionError("BOS timestamp must be later than setup timestamp")
                entries.append(
                    EntryEvent(
                        model="Confirm",
                        direction=self.direction,
                        score=self.score,
                        entry_timestamp=timestamp,
                        setup_timestamp=self.setup_timestamp,
                        bos_timestamp=self.bos_timestamp,
                        retest_timestamp=self.retest_timestamp,
                        confirm_timestamp=self.confirm_timestamp,
                        htf_regime=self.htf_regime,
                        session_bucket=self.session_bucket,
                    )
                )
                self.counters.reached_entry += 1
                self._reset()
            elif invalid or bar_index - self.retest_bar > self.config.p12_expiry_bars:
                self._reset("confirm_failed_or_expiry")
        return entries


def _prepare_data(frame: pd.DataFrame, config: FrozenConfig) -> pd.DataFrame:
    data = frame.tz_convert(config.exchange_timezone).copy()
    data = add_base_indicators(data, config)
    data = add_previous_closed_htf_regime(data, config)
    crt = crt_reference_and_sweeps(data)
    data = data.join(crt)
    data["pivot_high_2_2"] = confirmed_pivots(data.high, 2, 2, "high")
    data["pivot_low_2_2"] = confirmed_pivots(data.low, 2, 2, "low")
    data["pivot_high_3_3"] = confirmed_pivots(data.high, 3, 3, "high")
    data["pivot_low_3_3"] = confirmed_pivots(data.low, 3, 3, "low")
    return data


def run_sequential_bos_backtest(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig = FrozenConfig(),
    seq_config: SequentialBosConfig = SequentialBosConfig(),
) -> tuple[BacktestResult, FunnelCounters]:
    if frame.empty:
        raise ValueError("market data is empty")
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)
    data = _prepare_data(frame, config)
    first_bar = data.index[0]
    last_bar_end = data.index[-1] + pd.Timedelta(config.chart_minutes, unit="m")
    coverage = (
        "FULL DATA"
        if first_bar <= start_ts and last_bar_end >= end_exclusive
        else "PARTIAL DATA"
    )

    structure_engine = StructureEngine(config)
    swing_22_engine = CausalSwingEngine(2, 2)
    swing_33_engine = CausalSwingEngine(3, 3)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    funnel = SequentialBosFunnel(config, seq_config)
    trades = TradeEngine(config)

    bars_in_window = 0
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
        swing_22 = swing_22_engine.step(
            bar_index=bar_index,
            timestamp=timestamp,
            index=data.index,
            close=float(row.close),
            pivot_high=float(row.pivot_high_2_2),
            pivot_low=float(row.pivot_low_2_2),
        )[:2]
        swing_33 = swing_33_engine.step(
            bar_index=bar_index,
            timestamp=timestamp,
            index=data.index,
            close=float(row.close),
            pivot_high=float(row.pivot_high_3_3),
            pivot_low=float(row.pivot_low_3_3),
        )[:2]
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
                swing_22=swing_22,
                swing_33=swing_33,
            )
            for entry in entry_events:
                trades.try_open(
                    entry,
                    bar_index=bar_index,
                    close=float(row.close),
                    atr=float(row.atr),
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
        else pd.DataFrame(columns=TRADE_COLUMNS)
    )
    if not trade_frame.empty:
        trade_frame = trade_frame.sort_values(["exit_timestamp", "model"], kind="stable").reset_index(drop=True)

    diagnostics: Dict[str, object] = {
        "architecture": "SEQUENTIAL_BOS",
        "bos_definition": seq_config.bos_definition.value,
        "setup_bos_expiry_bars": seq_config.setup_bos_expiry_bars,
        "Bars In Window": bars_in_window,
        "Confirm Attempts": trades.attempts["Confirm"],
        "Confirm Accepted": trades.accepted["Confirm"],
        **funnel.counters.export(),
    }
    result = BacktestResult(
        trades=trade_frame,
        events=pd.DataFrame(),
        diagnostics=diagnostics,
        coverage=coverage,
        start_timestamp=start_ts,
        end_exclusive=end_exclusive,
    )
    return result, funnel.counters


def apply_costs(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return trades.copy()
    working = trades.copy()
    risk_points = (working.entry_price.astype(float) - working.stop_price.astype(float)).abs()
    cost_r = ROUND_TURN_COST_USD / (risk_points * NQ_DOLLARS_PER_POINT)
    working["gross_R"] = working.result_R.astype(float)
    working["net_R"] = working.gross_R - cost_r
    return working


def summarize_architecture(trades: pd.DataFrame, *, direction_split: bool = True) -> Dict[str, Any]:
    if trades.empty:
        base = {
            "N": 0,
            "wins": 0,
            "losses": 0,
            "WR": 0.0,
            "gross_AvgR": 0.0,
            "net_AvgR": 0.0,
            "gross_TotalR": 0.0,
            "net_TotalR": 0.0,
            "gross_PF": 0.0,
            "net_PF": 0.0,
            "MaxDD": 0.0,
        }
        if direction_split:
            base.update(
                {
                    "Long_N": 0,
                    "Long_AvgR": 0.0,
                    "Long_PF": 0.0,
                    "Short_N": 0,
                    "Short_AvgR": 0.0,
                    "Short_PF": 0.0,
                }
            )
        return base

    base = _summarize_with_costs(trades)
    summary = dict(base)
    if direction_split:
        for label, direction in (("Long", "Long"), ("Short", "Short")):
            group = trades.loc[trades.direction == direction]
            if group.empty:
                summary[f"{label}_N"] = 0
                summary[f"{label}_AvgR"] = 0.0
                summary[f"{label}_PF"] = 0.0
            else:
                group_summary = _summarize_with_costs(group)
                summary[f"{label}_N"] = int(group_summary["N"])
                summary[f"{label}_AvgR"] = float(group_summary["net_AvgR"])
                summary[f"{label}_PF"] = float(group_summary["net_PF"])
    return summary


def verify_completed_trade_ordering(trades: pd.DataFrame, data_index: pd.DatetimeIndex) -> None:
    if trades.empty:
        return
    index_map = {timestamp: idx for idx, timestamp in enumerate(data_index)}
    for row in trades.itertuples():
        setup_idx = index_map.get(pd.Timestamp(row.setup_timestamp))
        bos_idx = index_map.get(pd.Timestamp(row.bos_timestamp))
        retest_idx = index_map.get(pd.Timestamp(row.retest_timestamp))
        confirm_idx = index_map.get(pd.Timestamp(row.confirm_timestamp))
        entry_idx = index_map.get(pd.Timestamp(row.entry_timestamp))
        if None in (setup_idx, bos_idx, retest_idx, confirm_idx, entry_idx):
            raise AssertionError(f"missing bar mapping for trade {row}")
        assert_strict_order(
            setup_bar=setup_idx,
            bos_bar=bos_idx,
            retest_bar=retest_idx,
            confirm_bar=confirm_idx,
            entry_bar=entry_idx,
        )


def verify_retest_gated_parity(
    trades: pd.DataFrame,
    archived_trade_path: Path,
) -> None:
    archived = pd.read_csv(archived_trade_path)
    verify_archived_baseline(trades, archived)


def run_comparison_study(
    frame: pd.DataFrame,
    *,
    start: str = "2024-01-01",
    end: str = "2026-06-26",
    config: FrozenConfig = FrozenConfig(),
    archived_trade_path: Path,
    output: Path,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    prepared = _prepare_data(frame, config)
    frozen = run_backtest(frame, start=start, end=end, config=config)
    verify_retest_gated_parity(frozen.trades, archived_trade_path)

    original_trades = frozen.trades.loc[frozen.trades.model == "Control"].copy()
    retest_trades = frozen.trades.loc[frozen.trades.model == "Confirm"].copy()
    rows: List[Dict[str, Any]] = []
    funnel_rows: List[Dict[str, Any]] = []

    rows.append({"architecture": "ORIGINAL", "variant": "Control", **summarize_architecture(original_trades)})
    rows.append({"architecture": "RETEST_GATED", "variant": "Confirm", **summarize_architecture(retest_trades)})

    variants: List[tuple[BosDefinition, Optional[int]]] = []
    for bos_definition in BosDefinition:
        for expiry in SETUP_BOS_EXPIRY_OPTIONS:
            variants.append((bos_definition, expiry))

    best: Optional[Dict[str, Any]] = None
    for bos_definition, expiry in variants:
        seq_config = SequentialBosConfig(
            bos_definition=bos_definition,
            setup_bos_expiry_bars=expiry,
        )
        result, counters = run_sequential_bos_backtest(
            frame,
            start=start,
            end=end,
            config=config,
            seq_config=seq_config,
        )
        trades = result.trades.loc[result.trades.model == "Confirm"].copy()
        summary = summarize_architecture(trades)
        variant_name = f"{bos_definition.value}|expiry={expiry}"
        row = {
            "architecture": "SEQUENTIAL_BOS",
            "variant": variant_name,
            "bos_definition": bos_definition.value,
            "setup_bos_expiry_bars": expiry,
            **summary,
        }
        rows.append(row)
        funnel_rows.append(
            {
                "variant": variant_name,
                "bos_definition": bos_definition.value,
                "setup_bos_expiry_bars": expiry,
                **counters.export(),
            }
        )
        trades.to_csv(output / f"trades_{bos_definition.value}_{expiry}.csv", index=False)
        verify_completed_trade_ordering(trades, data_index=prepared.index)
        if best is None or summary["net_TotalR"] > best["net_TotalR"]:
            best = {**row, "funnel": counters.export()}

    comparison = pd.DataFrame(rows)
    funnels = pd.DataFrame(funnel_rows)
    comparison.to_csv(output / "architecture_comparison.csv", index=False)
    funnels.to_csv(output / "funnel_report.csv", index=False)

    robustness_rows: List[Dict[str, Any]] = []
    if best is not None and best["net_AvgR"] > 0 and best["net_PF"] > 1:
        best_trades = pd.read_csv(
            output / f"trades_{best['bos_definition']}_{best['setup_bos_expiry_bars']}.csv"
        )
        enriched = apply_costs(best_trades.sort_values("exit_timestamp"))
        entry_ts = pd.to_datetime(enriched.entry_timestamp, utc=True).dt.tz_convert(config.exchange_timezone)
        enriched["year"] = entry_ts.dt.year
        for year, group in enriched.groupby("year"):
            perf = summarize_architecture(group, direction_split=False)
            robustness_rows.append({"slice": f"year_{year}", **perf})
        chronological_split = len(enriched) // 2
        for label, group in (
            ("first_half", enriched.iloc[:chronological_split]),
            ("second_half", enriched.iloc[chronological_split:]),
        ):
            robustness_rows.append({"slice": label, **summarize_architecture(group, direction_split=False)})
        without_best = enriched.drop(enriched.net_R.idxmax())
        robustness_rows.append(
            {"slice": "remove_best_trade", **summarize_architecture(without_best, direction_split=False)}
        )
        cutoff = enriched.net_R.quantile(0.99)
        without_top = enriched.loc[enriched.net_R <= cutoff]
        robustness_rows.append(
            {"slice": "remove_top_1pct_winners", **summarize_architecture(without_top, direction_split=False)}
        )
        expiry = int(best["setup_bos_expiry_bars"])
        for neighbor in sorted({exp for exp in SETUP_BOS_EXPIRY_OPTIONS if abs(exp - expiry) <= 6}):
            neighbor_row = comparison.loc[
                (comparison.architecture == "SEQUENTIAL_BOS")
                & (comparison.bos_definition == best["bos_definition"])
                & (comparison.setup_bos_expiry_bars == neighbor)
            ]
            if not neighbor_row.empty:
                robustness_rows.append(
                    {
                        "slice": f"neighbor_expiry_{neighbor}",
                        **neighbor_row.iloc[0].to_dict(),
                    }
                )
        pd.DataFrame(robustness_rows).to_csv(output / "limited_robustness.csv", index=False)

    manifest = {
        "baseline_original": summarize_architecture(original_trades),
        "baseline_retest_gated": summarize_architecture(retest_trades),
        "best_sequential_variant": best,
        "classification": classify_architecture(best, summarize_architecture(retest_trades)),
    }
    (output / "study_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest


def classify_architecture(
    best: Optional[Dict[str, Any]],
    retest_gated: Dict[str, Any],
) -> str:
    if best is None:
        return "D — worse than current approach"
    improved = (
        best["net_AvgR"] > 0
        and best["net_PF"] > 1
        and best["net_TotalR"] > retest_gated["net_TotalR"]
        and best["N"] >= 30
    )
    if not improved:
        return "D — worse than current approach"
    if best["net_AvgR"] > retest_gated["net_AvgR"] + 0.05 and best["net_PF"] > retest_gated["net_PF"] + 0.1:
        return "A — sequential BOS materially improves architecture"
    if best["net_AvgR"] > 0 and best["net_PF"] > 1:
        return "B — promising but insufficient"
    return "C — no meaningful improvement"
