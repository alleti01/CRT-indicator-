"""Development-only Retest-Reclaim hypothesis test.

This module deliberately imports and consumes the frozen Phase 3/4/5 engines.
It does not modify the production funnel, settings, or Pine implementation.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .backtest import run_backtest, validation_window
from .config import FrozenConfig
from .indicators import (
    add_base_indicators,
    add_previous_closed_htf_regime,
    crt_reference_and_sweeps,
    htf_regime_name,
    score_band,
    session_bucket_name,
)
from .liquidity import LiquidityEngine
from .metrics import summarize_group
from .models import SetupEvent, StructureEvent
from .setup_engine import SetupEngine
from .structure import StructureEngine


SPECIAL_IDS = (228, 250, 117, 195, 86, 72, 149, 140, 84, 133, 252, 221)
PENETRATION_GRID = (0.10, 0.20, 0.30, 0.40, 0.50)
RECLAIM_WINDOW_GRID = (1, 2, 3, 4)
ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _key(direction: int, timestamp: pd.Timestamp) -> tuple[int, int]:
    return int(direction), int(pd.Timestamp(timestamp).value)


def _direction(value: Any) -> int:
    if isinstance(value, str):
        return 1 if value.lower() == "long" else -1
    return int(value)


@dataclass
class PreparedResearch:
    data: pd.DataFrame
    setups: List[SetupEvent]
    structures: List[StructureEvent]
    start_timestamp: pd.Timestamp
    end_exclusive: pd.Timestamp
    start_position: int
    end_position: int


def prepare_research(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig,
) -> PreparedResearch:
    """Warm the exact frozen engines once and retain their per-bar events."""
    data = frame.tz_convert(config.exchange_timezone).sort_index().copy()
    data = add_base_indicators(data, config)
    data = add_previous_closed_htf_regime(data, config)
    data = data.join(crt_reference_and_sweeps(data))
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)

    structure_engine = StructureEngine(config)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    structures: List[StructureEvent] = []
    setups: List[SetupEvent] = []
    for bar_index, row in enumerate(data.itertuples()):
        structure = structure_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.structure_pivot_high),
            pivot_low=float(row.structure_pivot_low),
        )
        liquidity = liquidity_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.liquidity_pivot_high),
            pivot_low=float(row.liquidity_pivot_low),
        )
        setup = setup_engine.step(
            bar_index=bar_index,
            timestamp=row.Index,
            open_price=float(row.open),
            close=float(row.close),
            atr=float(row.atr),
            body_average=float(row.body_sma),
            htf_regime=int(row.htf_regime),
            structure=structure,
            liquidity=liquidity,
        )
        structures.append(structure)
        setups.append(setup)

    start_pos = int(data.index.searchsorted(start_ts, side="left"))
    end_pos = int(data.index.searchsorted(end_exclusive, side="left"))
    return PreparedResearch(
        data=data,
        setups=setups,
        structures=structures,
        start_timestamp=start_ts,
        end_exclusive=end_exclusive,
        start_position=start_pos,
        end_position=end_pos,
    )


@dataclass
class ReclaimEntry:
    candidate_id: int
    direction: int
    score: float
    setup_timestamp: pd.Timestamp
    bos_timestamp: pd.Timestamp
    retest_timestamp: pd.Timestamp
    reclaim_timestamp: pd.Timestamp
    entry_timestamp: pd.Timestamp
    htf_regime: int
    session_bucket: int


@dataclass
class ReclaimGate:
    """Preregistered research state machine with a distinct reclaim stage.

    Causal order is Setup -> BOS -> Retest touch -> later Reclaim -> later
    existing Confirm. The touch bar cannot reclaim or confirm, and the reclaim
    bar cannot confirm.
    """

    config: FrozenConfig
    penetration_atr: float
    reclaim_window_bars: int
    candidate_lookup: Dict[tuple[int, int], int]
    state: int = 0  # 0 idle, 1 BOS, 2 retest, 3 reclaim, 4 confirm
    direction: int = 0
    setup_bar: int = -1
    bos_bar: int = -1
    retest_bar: int = -1
    reclaim_bar: int = -1
    bos_level: float = float("nan")
    score: float = 0.0
    candidate_id: int = -1
    setup_timestamp: Optional[pd.Timestamp] = None
    bos_timestamp: Optional[pd.Timestamp] = None
    retest_timestamp: Optional[pd.Timestamp] = None
    reclaim_timestamp: Optional[pd.Timestamp] = None
    transitions: List[Dict[str, Any]] = field(default_factory=list)
    outcomes: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def variant(self) -> str:
        return f"P{self.penetration_atr:.2f}_W{self.reclaim_window_bars}"

    def _log(self, *, timestamp: pd.Timestamp, bar_index: int, event: str, **details: Any) -> None:
        self.transitions.append(
            {
                "variant": self.variant,
                "candidate_id": self.candidate_id,
                "timestamp": timestamp,
                "bar_index": bar_index,
                "event": event,
                **details,
            }
        )

    def _finish(self, timestamp: pd.Timestamp, bar_index: int, result: str) -> None:
        if self.candidate_id >= 0:
            self.outcomes.append(
                {
                    "variant": self.variant,
                    "candidate_id": self.candidate_id,
                    "direction": "Long" if self.direction == 1 else "Short",
                    "setup_timestamp": self.setup_timestamp,
                    "bos_timestamp": self.bos_timestamp,
                    "retest_timestamp": self.retest_timestamp,
                    "reclaim_timestamp": self.reclaim_timestamp,
                    "terminal_timestamp": timestamp,
                    "terminal_bar_index": bar_index,
                    "gate_result": result,
                }
            )
        self.state = 0
        self.direction = 0
        self.candidate_id = -1
        self.bos_level = float("nan")

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
    ) -> Optional[ReclaimEntry]:
        if setup.canonical and self.state == 0:
            self.state = 1
            self.direction = setup.canonical_direction
            self.setup_bar = bar_index
            self.bos_bar = self.retest_bar = self.reclaim_bar = -1
            self.bos_level = float("nan")
            self.score = float(setup.canonical_score)
            self.setup_timestamp = timestamp
            self.bos_timestamp = self.retest_timestamp = self.reclaim_timestamp = None
            self.candidate_id = self.candidate_lookup.get(
                _key(self.direction, timestamp), -1
            )
            self._log(timestamp=timestamp, bar_index=bar_index, event="SETUP_ACCEPTED")

        # Separate ``if`` preserves the frozen same-bar Setup + matching BOS.
        if self.state == 1:
            matching = (self.direction == 1 and structure.bull_bos) or (
                self.direction == -1 and structure.bear_bos
            )
            opposite = (self.direction == 1 and structure.bear_bos) or (
                self.direction == -1 and structure.bull_bos
            )
            if matching:
                prior = (
                    structure.previous_active_high
                    if self.direction == 1
                    else structure.previous_active_low
                )
                current = structure.active_high if self.direction == 1 else structure.active_low
                self.bos_level = float(prior if _finite(prior) else current)
                self.bos_bar = bar_index
                self.bos_timestamp = timestamp
                self.state = 2
                self._log(
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="BOS_ACCEPTED",
                    bos_level=self.bos_level,
                    same_bar_setup_bos=bar_index == self.setup_bar,
                )
            elif opposite:
                self._finish(timestamp, bar_index, "OPPOSITE_BOS_WAIT_BOS")
            elif bar_index - self.setup_bar > self.config.p12_expiry_bars:
                self._finish(timestamp, bar_index, "BOS_EXPIRED")

        elif self.state == 2 and _finite(self.bos_level):
            atr_used = float(atr) if _finite(atr) else 1.0
            touch_tolerance = atr_used * self.config.p12_retest_atr_tolerance
            penetration = atr_used * self.penetration_atr
            eligible = self.bos_bar >= 0 and bar_index > self.bos_bar
            touched = eligible and (
                low <= self.bos_level + touch_tolerance
                if self.direction == 1
                else high >= self.bos_level - touch_tolerance
            )
            exceeded = eligible and (
                close < self.bos_level - penetration
                if self.direction == 1
                else close > self.bos_level + penetration
            )
            opposite = (self.direction == 1 and structure.bear_bos) or (
                self.direction == -1 and structure.bull_bos
            )
            if opposite:
                self._finish(timestamp, bar_index, "OPPOSITE_BOS_WAIT_RETEST")
            elif exceeded:
                self._finish(timestamp, bar_index, "MAX_PENETRATION_WAIT_RETEST")
            elif touched:
                self.retest_bar = bar_index
                self.retest_timestamp = timestamp
                self.state = 3
                self._log(
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="RETEST_TOUCH_ACCEPTED",
                    bos_level=self.bos_level,
                    touch_tolerance=touch_tolerance,
                    penetration_limit=penetration,
                )
            elif bar_index - self.bos_bar > self.config.p12_expiry_bars:
                self._finish(timestamp, bar_index, "RETEST_EXPIRED")

        elif self.state == 3 and _finite(self.bos_level):
            atr_used = float(atr) if _finite(atr) else 1.0
            penetration = atr_used * self.penetration_atr
            eligible = self.retest_bar >= 0 and bar_index > self.retest_bar
            exceeded = eligible and (
                close < self.bos_level - penetration
                if self.direction == 1
                else close > self.bos_level + penetration
            )
            reclaimed = eligible and (
                (close > open_price and close > self.bos_level)
                if self.direction == 1
                else (close < open_price and close < self.bos_level)
            )
            opposite = (self.direction == 1 and structure.bear_bos) or (
                self.direction == -1 and structure.bull_bos
            )
            if opposite:
                self._finish(timestamp, bar_index, "OPPOSITE_BOS_WAIT_RECLAIM")
            elif exceeded:
                self._finish(timestamp, bar_index, "MAX_PENETRATION_WAIT_RECLAIM")
            elif reclaimed:
                self.reclaim_bar = bar_index
                self.reclaim_timestamp = timestamp
                self.state = 4
                self._log(
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="RECLAIM_ACCEPTED",
                    bos_level=self.bos_level,
                    penetration_limit=penetration,
                )
            elif bar_index - self.retest_bar >= self.reclaim_window_bars:
                self._finish(timestamp, bar_index, "RECLAIM_EXPIRED")

        elif self.state == 4 and _finite(self.bos_level):
            atr_used = float(atr) if _finite(atr) else 1.0
            tolerance = atr_used * self.config.p12_retest_atr_tolerance
            eligible = self.reclaim_bar >= 0 and bar_index > self.reclaim_bar
            confirmed = eligible and (
                (close > open_price and close > self.bos_level)
                if self.direction == 1
                else (close < open_price and close < self.bos_level)
            )
            invalid = eligible and (
                close < self.bos_level - tolerance
                if self.direction == 1
                else close > self.bos_level + tolerance
            )
            opposite = (self.direction == 1 and structure.bear_bos) or (
                self.direction == -1 and structure.bull_bos
            )
            if opposite:
                self._finish(timestamp, bar_index, "OPPOSITE_BOS_WAIT_CONFIRM")
            elif confirmed:
                if self.setup_timestamp is None or self.bos_timestamp is None or self.retest_timestamp is None or self.reclaim_timestamp is None:
                    raise RuntimeError("reclaim entry lost its causal parent timestamps")
                entry = ReclaimEntry(
                    candidate_id=self.candidate_id,
                    direction=self.direction,
                    score=self.score,
                    setup_timestamp=self.setup_timestamp,
                    bos_timestamp=self.bos_timestamp,
                    retest_timestamp=self.retest_timestamp,
                    reclaim_timestamp=self.reclaim_timestamp,
                    entry_timestamp=timestamp,
                    htf_regime=int(setup.htf_regime),
                    session_bucket=int(setup.session_bucket),
                )
                self._log(timestamp=timestamp, bar_index=bar_index, event="CONFIRM_ENTRY")
                self._finish(timestamp, bar_index, "ENTRY")
                return entry
            elif invalid:
                self._finish(timestamp, bar_index, "CONFIRMATION_INVALID")
            elif bar_index - self.reclaim_bar > self.config.p12_expiry_bars:
                self._finish(timestamp, bar_index, "CONFIRMATION_EXPIRED")
        return None

    def finish_window(self, timestamp: pd.Timestamp, bar_index: int) -> None:
        if self.state:
            self._finish(timestamp, bar_index, "WINDOW_END")


@dataclass
class ResearchTradeEngine:
    config: FrozenConfig
    variant: str
    active: Optional[Dict[str, Any]] = None
    completed: List[Dict[str, Any]] = field(default_factory=list)
    attempts: int = 0
    accepted: int = 0

    def try_open(
        self,
        entry: ReclaimEntry,
        *,
        bar_index: int,
        close: float,
        atr: float,
    ) -> bool:
        self.attempts += 1
        if self.active is not None:
            return False
        atr_used = float(atr) if _finite(atr) else 1.0
        risk = self.config.trade_stop_atr * atr_used
        if risk <= 0:
            return False
        stop = close - risk if entry.direction == 1 else close + risk
        target = close + risk * self.config.trade_target_r if entry.direction == 1 else close - risk * self.config.trade_target_r
        self.active = {
            "variant": self.variant,
            "candidate_id": entry.candidate_id,
            "direction": "Long" if entry.direction == 1 else "Short",
            "direction_int": entry.direction,
            "score": entry.score,
            "setup_timestamp": entry.setup_timestamp,
            "bos_timestamp": entry.bos_timestamp,
            "retest_timestamp": entry.retest_timestamp,
            "reclaim_timestamp": entry.reclaim_timestamp,
            "confirm_timestamp": entry.entry_timestamp,
            "entry_timestamp": entry.entry_timestamp,
            "entry_bar": bar_index,
            "entry_price": float(close),
            "stop_price": float(stop),
            "target_price": float(target),
            "risk_points": float(risk),
            "htf_regime": entry.htf_regime,
            "session_bucket": entry.session_bucket,
            "mfe_R": 0.0,
            "mae_R": 0.0,
        }
        self.accepted += 1
        return True

    def _close(self, timestamp: pd.Timestamp, price: float, result_r: float, reason: str) -> None:
        if self.active is None:
            return
        trade = self.active
        trade["exit_timestamp"] = timestamp
        trade["exit_price"] = float(price)
        trade["gross_result_R"] = float(result_r)
        trade["cost_R"] = ROUND_TURN_COST_USD / (trade["risk_points"] * NQ_DOLLARS_PER_POINT)
        trade["net_result_R"] = trade["gross_result_R"] - trade["cost_R"]
        trade["exit_reason"] = reason
        trade.pop("direction_int", None)
        trade.pop("entry_bar", None)
        self.completed.append(trade)
        self.active = None

    def manage(
        self,
        *,
        bar_index: int,
        timestamp: pd.Timestamp,
        bar_end: pd.Timestamp,
        high: float,
        low: float,
        close: float,
        end_exclusive: pd.Timestamp,
    ) -> None:
        if self.active is None:
            return
        trade = self.active
        elapsed = bar_index - int(trade["entry_bar"])
        if elapsed < 1:
            return
        risk = float(trade["risk_points"])
        entry = float(trade["entry_price"])
        direction = int(trade["direction_int"])
        favorable = (high - entry) / risk if direction == 1 else (entry - low) / risk
        adverse = (entry - low) / risk if direction == 1 else (high - entry) / risk
        trade["mfe_R"] = max(float(trade["mfe_R"]), float(favorable))
        trade["mae_R"] = max(float(trade["mae_R"]), float(adverse))

        result: Optional[float] = None
        price: Optional[float] = None
        reason = ""
        if direction == 1:
            if low <= trade["stop_price"]:
                result, price, reason = -1.0, trade["stop_price"], "STOP"
            elif high >= trade["target_price"]:
                result, price, reason = self.config.trade_target_r, trade["target_price"], "TARGET"
            elif elapsed >= self.config.trade_max_bars:
                result, price, reason = (close - entry) / risk, close, "TIME"
            elif bar_end >= end_exclusive:
                result, price, reason = (close - entry) / risk, close, "WINDOW_END"
        else:
            if high >= trade["stop_price"]:
                result, price, reason = -1.0, trade["stop_price"], "STOP"
            elif low <= trade["target_price"]:
                result, price, reason = self.config.trade_target_r, trade["target_price"], "TARGET"
            elif elapsed >= self.config.trade_max_bars:
                result, price, reason = (entry - close) / risk, close, "TIME"
            elif bar_end >= end_exclusive:
                result, price, reason = (entry - close) / risk, close, "WINDOW_END"
        if result is not None and price is not None:
            self._close(timestamp, float(price), float(result), reason)

    def finish_window(self, timestamp: pd.Timestamp, close: float) -> None:
        if self.active is None:
            return
        entry = float(self.active["entry_price"])
        risk = float(self.active["risk_points"])
        direction = int(self.active["direction_int"])
        result = (close - entry) / risk if direction == 1 else (entry - close) / risk
        self._close(timestamp, close, result, "WINDOW_END")


def _metric_row(
    trades: pd.DataFrame,
    *,
    result_column: str,
) -> Dict[str, Any]:
    working = trades.copy()
    if working.empty:
        working = pd.DataFrame(columns=["result_R"])
    else:
        working["result_R"] = working[result_column].astype(float)
        working = working.sort_values("exit_timestamp", kind="stable")
    metrics = summarize_group(working)
    metrics["avg_MFE_R"] = float(trades["mfe_R"].mean()) if not trades.empty and "mfe_R" in trades else 0.0
    metrics["avg_MAE_R"] = float(trades["mae_R"].mean()) if not trades.empty and "mae_R" in trades else 0.0
    return metrics


def _add_current_excursions(current: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    if current.empty:
        return current
    result = current.copy()
    result["risk_points"] = (result["entry_price"] - result["stop_price"]).abs()
    mfe_values: List[float] = []
    mae_values: List[float] = []
    for trade in result.itertuples():
        start = pd.Timestamp(trade.entry_timestamp)
        finish = pd.Timestamp(trade.exit_timestamp)
        path = data.loc[(data.index > start) & (data.index <= finish)]
        risk = float(trade.risk_points)
        if path.empty or risk <= 0:
            mfe_values.append(0.0)
            mae_values.append(0.0)
        elif trade.direction == "Long":
            mfe_values.append(max(0.0, float((path.high.max() - trade.entry_price) / risk)))
            mae_values.append(max(0.0, float((trade.entry_price - path.low.min()) / risk)))
        else:
            mfe_values.append(max(0.0, float((trade.entry_price - path.low.min()) / risk)))
            mae_values.append(max(0.0, float((path.high.max() - trade.entry_price) / risk)))
    result["mfe_R"] = mfe_values
    result["mae_R"] = mae_values
    result["gross_result_R"] = result["result_R"].astype(float)
    result["cost_R"] = ROUND_TURN_COST_USD / (result["risk_points"] * NQ_DOLLARS_PER_POINT)
    result["net_result_R"] = result["gross_result_R"] - result["cost_R"]
    result["variant"] = "CURRENT"
    return result


def _breakdowns(trades: pd.DataFrame, variant: str, result_column: str) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    working = trades.copy()
    working["direction_bucket"] = working["direction"].astype(str)
    working["score_band"] = working["score"].map(score_band)
    working["session"] = working["session_bucket"].map(session_bucket_name)
    working["HTF_regime"] = working["htf_regime"].map(htf_regime_name)
    rows: List[Dict[str, Any]] = []
    for dimension, column in {
        "direction": "direction_bucket",
        "score_band": "score_band",
        "session": "session",
        "HTF_regime": "HTF_regime",
    }.items():
        for bucket, group in working.groupby(column, sort=True):
            rows.append(
                {
                    "variant": variant,
                    "basis": "net_after_14.50_USD",
                    "dimension": dimension,
                    "bucket": str(bucket),
                    **_metric_row(group, result_column=result_column),
                }
            )
    return pd.DataFrame(rows)


def run_reclaim_grid(
    prepared: PreparedResearch,
    *,
    config: FrozenConfig,
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    lookup = {
        _key(_direction(row.direction), pd.Timestamp(row.setup_timestamp)): int(row.candidate_id)
        for row in candidates.itertuples()
    }
    gates: List[ReclaimGate] = []
    engines: Dict[str, ResearchTradeEngine] = {}
    for penetration in PENETRATION_GRID:
        for window in RECLAIM_WINDOW_GRID:
            gate = ReclaimGate(config, penetration, window, lookup)
            gates.append(gate)
            engines[gate.variant] = ResearchTradeEngine(config, gate.variant)

    last_timestamp = prepared.start_timestamp
    last_close = float("nan")
    last_bar = prepared.start_position
    for bar_index in range(prepared.start_position, prepared.end_position):
        row = prepared.data.iloc[bar_index]
        timestamp = prepared.data.index[bar_index]
        setup = prepared.setups[bar_index]
        structure = prepared.structures[bar_index]
        for gate in gates:
            entry = gate.step(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=float(row.atr),
                setup=setup,
                structure=structure,
            )
            engine = engines[gate.variant]
            if entry is not None:
                accepted = engine.try_open(
                    entry,
                    bar_index=bar_index,
                    close=float(row.close),
                    atr=float(row.atr),
                )
                if gate.outcomes:
                    gate.outcomes[-1]["trade_accepted"] = accepted
            engine.manage(
                bar_index=bar_index,
                timestamp=timestamp,
                bar_end=timestamp + pd.Timedelta(config.chart_minutes, unit="m"),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                end_exclusive=prepared.end_exclusive,
            )
        last_timestamp, last_close, last_bar = timestamp, float(row.close), bar_index

    for gate in gates:
        gate.finish_window(last_timestamp, last_bar)
        engines[gate.variant].finish_window(last_timestamp, last_close)

    trades = pd.DataFrame(
        [trade for engine in engines.values() for trade in engine.completed]
    )
    outcomes = pd.DataFrame([row for gate in gates for row in gate.outcomes])
    transitions = pd.DataFrame([row for gate in gates for row in gate.transitions])
    summary_rows: List[Dict[str, Any]] = []
    breakdown_frames: List[pd.DataFrame] = []
    for gate in gates:
        group = trades.loc[trades.variant == gate.variant].copy() if not trades.empty else pd.DataFrame()
        engine = engines[gate.variant]
        summary_rows.append(
            {
                "variant": gate.variant,
                "penetration_atr": gate.penetration_atr,
                "reclaim_window_bars": gate.reclaim_window_bars,
                "entry_attempts": engine.attempts,
                "entry_accepted": engine.accepted,
                **{f"gross_{k}": v for k, v in _metric_row(group, result_column="gross_result_R").items()},
                **{f"net_{k}": v for k, v in _metric_row(group, result_column="net_result_R").items()},
            }
        )
        breakdown_frames.append(_breakdowns(group, gate.variant, "net_result_R"))
    breakdowns = pd.concat(breakdown_frames, ignore_index=True) if breakdown_frames else pd.DataFrame()
    return pd.DataFrame(summary_rows), trades, outcomes, pd.concat([transitions, breakdowns], ignore_index=True, sort=False)


def _trace_current_candidate(
    candidate: pd.Series,
    prepared: PreparedResearch,
    config: FrozenConfig,
) -> List[Dict[str, Any]]:
    bos_bar = int(candidate.bos_bar_index)
    terminal_bar = int(candidate.terminal_bar_index)
    direction = _direction(candidate.direction)
    level = float(candidate.bos_level_stored)
    state = "WAIT_RETEST"
    retest_bar = -1
    rows: List[Dict[str, Any]] = []
    for bar_index in range(bos_bar, terminal_bar + 1):
        bar = prepared.data.iloc[bar_index]
        timestamp = prepared.data.index[bar_index]
        structure = prepared.structures[bar_index]
        atr = float(bar.atr) if _finite(bar.atr) else 1.0
        tolerance = atr * config.p12_retest_atr_tolerance
        lower, upper = level - tolerance, level + tolerance
        before = "WAIT_BOS" if bar_index == bos_bar else state
        eligible_retest = state == "WAIT_RETEST" and bar_index > bos_bar
        touch = eligible_retest and (float(bar.low) <= upper if direction == 1 else float(bar.high) >= lower)
        invalid_retest = eligible_retest and (float(bar.close) < lower if direction == 1 else float(bar.close) > upper)
        eligible_confirm = state == "WAIT_CONFIRM" and bar_index > retest_bar
        directional = float(bar.close) > float(bar.open) if direction == 1 else float(bar.close) < float(bar.open)
        beyond_level = float(bar.close) > level if direction == 1 else float(bar.close) < level
        confirmed = eligible_confirm and directional and beyond_level
        invalid_confirm = eligible_confirm and (float(bar.close) < lower if direction == 1 else float(bar.close) > upper)
        opposite = (direction == 1 and structure.bear_bos) or (direction == -1 and structure.bull_bos)
        reason = ""
        after = before
        if bar_index == bos_bar:
            after = state = "WAIT_RETEST"
            reason = "MATCHING_BOS_ACCEPTED"
        elif state == "WAIT_RETEST":
            if opposite:
                after, state, reason = "IDLE", "IDLE", "OPPOSITE_BOS_WAIT_RETEST"
            elif invalid_retest:
                after, state, reason = "IDLE", "IDLE", "RETEST_STRUCTURE_FAILED"
            elif touch:
                retest_bar = bar_index
                after, state, reason = "WAIT_CONFIRM", "WAIT_CONFIRM", "RETEST_ACCEPTED"
            elif bar_index - bos_bar > config.p12_expiry_bars:
                after, state, reason = "IDLE", "IDLE", "NO_VALID_RETEST"
            else:
                after = state
        elif state == "WAIT_CONFIRM":
            if opposite:
                after, state, reason = "IDLE", "IDLE", "OPPOSITE_BOS_WAIT_CONFIRM"
            elif confirmed:
                after, state, reason = "IDLE", "IDLE", "CONFIRM_ENTRY"
            elif invalid_confirm:
                after, state, reason = "IDLE", "IDLE", "CONFIRMATION_STRUCTURE_FAILED"
            elif bar_index - retest_bar > config.p12_expiry_bars:
                after, state, reason = "IDLE", "IDLE", "NO_CONFIRMATION"
            else:
                after = state
        rows.append(
            {
                "candidate_id": int(candidate.candidate_id),
                "direction": candidate.direction,
                "timestamp": timestamp,
                "bar_index": bar_index,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "atr": atr,
                "bos_level": level,
                "tolerance_0.10_atr": tolerance,
                "lower_threshold": lower,
                "upper_threshold": upper,
                "bull_bos": bool(structure.bull_bos),
                "bear_bos": bool(structure.bear_bos),
                "state_before": before,
                "eligible_retest": eligible_retest,
                "retest_touch": touch,
                "retest_accepted": reason == "RETEST_ACCEPTED",
                "retest_invalid": invalid_retest,
                "eligible_confirm": eligible_confirm,
                "confirmation_evaluated": eligible_confirm,
                "confirmation_bearish_candle": directional if direction == -1 else np.nan,
                "confirmation_close_below_bos": beyond_level if direction == -1 else np.nan,
                "directional_candle": directional,
                "close_beyond_bos": beyond_level,
                "confirmation": confirmed,
                "confirmation_invalid": invalid_confirm,
                "invalidation": bool(opposite or invalid_retest or invalid_confirm),
                "opposite_bos": opposite,
                "state_after": after,
                "transition_reason": reason,
            }
        )
    return rows


def build_forensic_audit(
    *,
    prepared: PreparedResearch,
    candidates: pd.DataFrame,
    near_misses: pd.DataFrame,
    config: FrozenConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    selected = candidates.loc[candidates.candidate_id.isin(SPECIAL_IDS)].copy()
    trace_rows: List[Dict[str, Any]] = []
    for row in selected.itertuples(index=False):
        trace_rows.extend(_trace_current_candidate(pd.Series(row._asdict()), prepared, config))
    trace = pd.DataFrame(trace_rows)
    audits: List[Dict[str, Any]] = []
    for row in selected.itertuples(index=False):
        old = near_misses.loc[near_misses.candidate_id == row.candidate_id].iloc[0]
        terminal = trace.loc[
            (trace.candidate_id == row.candidate_id)
            & (trace.bar_index == int(row.terminal_bar_index))
        ].iloc[-1]
        proxy_ts = pd.Timestamp(old.would_be_confirmation_timestamp)
        terminal_ts = pd.Timestamp(row.terminal_timestamp)
        classification = (
            "D_DIAGNOSTIC_PROXY_LABEL_BUG"
            if proxy_ts.value != terminal_ts.value
            else "B_REASON_FROM_TERMINAL_BAR"
        )
        relative_order = (
            "TERMINAL_BEFORE_PROXY"
            if terminal_ts < proxy_ts
            else "TERMINAL_AFTER_PROXY"
            if terminal_ts > proxy_ts
            else "SAME_BAR"
        )
        audits.append(
            {
                "candidate_id": int(row.candidate_id),
                "direction": row.direction,
                "setup_timestamp": row.setup_timestamp,
                "bos_timestamp": row.bos_timestamp,
                "bos_level": row.bos_level_stored,
                "diagnostic_proxy_timestamp": proxy_ts,
                "diagnostic_proxy_close": float(old.would_be_confirmation_close),
                "actual_terminal_timestamp": terminal_ts,
                "actual_terminal_close": float(terminal.close),
                "actual_terminal_state_before": terminal.state_before,
                "actual_terminal_state_after": terminal.state_after,
                "actual_terminal_threshold": (
                    terminal.upper_threshold if row.direction == "Short" else terminal.lower_threshold
                ),
                "actual_terminal_reason": terminal.transition_reason,
                "reported_rejection_detail": row.first_failure_detail,
                "proxy_is_actual_terminal_bar": proxy_ts.value == terminal_ts.value,
                "A_wrong_bar_selected_for_reported_confirmation": proxy_ts.value != terminal_ts.value,
                "B_rejection_reason_is_from_actual_terminal_bar": True,
                "C_state_was_invalidated_before_displayed_proxy": terminal_ts < proxy_ts,
                "D_diagnostic_reporting_bug": proxy_ts.value != terminal_ts.value,
                "E_strategy_logic_bug": False,
                "terminal_vs_proxy_order": relative_order,
                "classification": classification,
                "diagnostic_MFE_ATR": float(old.mfe_atr),
                "diagnostic_MAE_ATR": float(old.mae_atr),
            }
        )
    return trace, pd.DataFrame(audits)


def attach_candidate_ids(current: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    mapping = {
        _key(_direction(row.direction), pd.Timestamp(row.entry_timestamp)): int(row.candidate_id)
        for row in candidates.loc[candidates.final_result == "ENTRY"].itertuples()
    }
    result = current.copy()
    result["candidate_id"] = [
        mapping.get(_key(_direction(row.direction), pd.Timestamp(row.entry_timestamp)), -1)
        for row in result.itertuples()
    ]
    return result


def special_candidate_matrix(
    *,
    audits: pd.DataFrame,
    trades: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for penetration in PENETRATION_GRID:
        for window in RECLAIM_WINDOW_GRID:
            variant = f"P{penetration:.2f}_W{window}"
            variant_trades = trades.loc[trades.variant == variant] if not trades.empty else trades
            variant_outcomes = outcomes.loc[outcomes.variant == variant] if not outcomes.empty else outcomes
            for audit in audits.itertuples():
                trade = variant_trades.loc[variant_trades.candidate_id == audit.candidate_id]
                outcome = variant_outcomes.loc[variant_outcomes.candidate_id == audit.candidate_id]
                trade_row = trade.iloc[0] if not trade.empty else None
                outcome_row = outcome.iloc[0] if not outcome.empty else None
                rows.append(
                    {
                        "variant": variant,
                        "penetration_atr": penetration,
                        "reclaim_window_bars": window,
                        "candidate_id": audit.candidate_id,
                        "current_result": "NO_ENTRY",
                        "reclaim_gate_result": outcome_row.gate_result if outcome_row is not None else "SETUP_NOT_ACCEPTED_WHILE_BUSY",
                        "reclaim_result": "ENTRY" if trade_row is not None else "NO_ENTRY",
                        "reclaim_entry_timestamp": trade_row.entry_timestamp if trade_row is not None else pd.NaT,
                        "gross_R": trade_row.gross_result_R if trade_row is not None else np.nan,
                        "net_R_after_14.50_USD": trade_row.net_result_R if trade_row is not None else np.nan,
                        "trade_MFE_R": trade_row.mfe_R if trade_row is not None else np.nan,
                        "trade_MAE_R": trade_row.mae_R if trade_row is not None else np.nan,
                        "current_diagnostic_MFE_ATR": audit.diagnostic_MFE_ATR,
                        "current_diagnostic_MAE_ATR": audit.diagnostic_MAE_ATR,
                    }
                )
    return pd.DataFrame(rows)


def select_quality_leader(summary: pd.DataFrame) -> tuple[pd.Series, bool, pd.DataFrame]:
    """Select by net PF, then DD, then AvgR; never by frequency/TotalR alone."""
    ranked = summary.sort_values(
        ["net_profit_factor", "net_max_drawdown_R", "net_avg_R"],
        ascending=[False, True, False],
        kind="stable",
    ).reset_index(drop=True)
    leader = ranked.iloc[0]
    neighbors = summary.loc[
        (summary.penetration_atr.sub(leader.penetration_atr).abs() <= 0.1000001)
        & (summary.reclaim_window_bars.sub(leader.reclaim_window_bars).abs() <= 1)
        & (summary.variant != leader.variant)
    ].copy()
    positive = (neighbors.net_avg_R > 0) & (neighbors.net_profit_factor > 1.0)
    robust = len(neighbors) >= 3 and float(positive.mean()) >= 0.75 and float(neighbors.net_avg_R.median()) > 0 and float(neighbors.net_profit_factor.median()) > 1.0
    neighbors["positive_net_edge"] = positive
    return leader, robust, neighbors


def run_research(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    output: Path,
    forensic_dir: Path,
    config: FrozenConfig = FrozenConfig(),
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    candidates = pd.read_csv(forensic_dir / "all_setup_candidates.csv")
    near_misses = pd.read_csv(forensic_dir / "near_miss_shorts.csv")
    for column in [c for c in candidates.columns if "timestamp" in c]:
        candidates[column] = pd.to_datetime(candidates[column], errors="coerce")
    for column in [c for c in near_misses.columns if "timestamp" in c]:
        near_misses[column] = pd.to_datetime(near_misses[column], errors="coerce")

    prepared = prepare_research(frame, start=start, end=end, config=config)
    trace, audit = build_forensic_audit(
        prepared=prepared,
        candidates=candidates,
        near_misses=near_misses,
        config=config,
    )
    trace.to_csv(output / "current_near_miss_bar_trace.csv", index=False)
    audit.to_csv(output / "diagnostic_bug_audit.csv", index=False)

    baseline = run_backtest(frame, start=start, end=end, config=config)
    current = baseline.trades.loc[baseline.trades.model == "Confirm"].copy()
    current = attach_candidate_ids(current, candidates)
    current = _add_current_excursions(current, prepared.data)
    current.to_csv(output / "current_confirm_trades.csv", index=False)

    grid, trades, outcomes, mixed = run_reclaim_grid(
        prepared, config=config, candidates=candidates
    )
    if not trades.empty:
        current_ids = set(current.candidate_id.astype(int))
        trades["recovered_vs_current"] = ~trades.candidate_id.astype(int).isin(current_ids)
        trades = trades.sort_values(["variant", "exit_timestamp"], kind="stable")
    trades.to_csv(output / "reclaim_trades.csv", index=False)
    outcomes.to_csv(output / "reclaim_candidate_outcomes.csv", index=False)
    transitions = mixed.loc[mixed.event.notna()].copy() if "event" in mixed else pd.DataFrame()
    breakdowns = mixed.loc[mixed.dimension.notna()].copy() if "dimension" in mixed else pd.DataFrame()
    breakdown_columns = [
        "variant", "basis", "dimension", "bucket", "N", "wins", "losses",
        "win_pct", "avg_R", "total_R", "profit_factor", "max_drawdown_R",
        "largest_win_R", "largest_loss_R", "max_consecutive_wins",
        "max_consecutive_losses", "avg_MFE_R", "avg_MAE_R",
    ]
    if not breakdowns.empty:
        breakdowns = breakdowns[breakdown_columns]
    transition_columns = [
        "variant", "candidate_id", "timestamp", "bar_index", "event",
        "bos_level", "same_bar_setup_bos", "touch_tolerance", "penetration_limit",
    ]
    if not transitions.empty:
        transitions = transitions[[column for column in transition_columns if column in transitions.columns]]
    transitions.to_csv(output / "reclaim_transitions.csv", index=False)
    breakdowns.to_csv(output / "reclaim_breakdowns.csv", index=False)

    recovered_rows: List[Dict[str, Any]] = []
    for row in grid.itertuples():
        group = trades.loc[(trades.variant == row.variant) & (trades.recovered_vs_current)] if not trades.empty else pd.DataFrame()
        recovered_rows.append(
            {
                "variant": row.variant,
                "penetration_atr": row.penetration_atr,
                "reclaim_window_bars": row.reclaim_window_bars,
                **{f"recovered_{k}": v for k, v in _metric_row(group, result_column="net_result_R").items()},
            }
        )
    recovered = pd.DataFrame(recovered_rows)
    grid = grid.merge(recovered, on=["variant", "penetration_atr", "reclaim_window_bars"], how="left")

    current_gross = _metric_row(current, result_column="gross_result_R")
    current_net = _metric_row(current, result_column="net_result_R")
    current_summary = pd.DataFrame(
        [{
            "variant": "CURRENT",
            "penetration_atr": np.nan,
            "reclaim_window_bars": np.nan,
            **{f"gross_{k}": v for k, v in current_gross.items()},
            **{f"net_{k}": v for k, v in current_net.items()},
        }]
    )
    comparison = pd.concat([current_summary, grid], ignore_index=True, sort=False)
    comparison.to_csv(output / "current_vs_reclaim_grid.csv", index=False)
    recovered.to_csv(output / "recovered_trade_summary.csv", index=False)
    pd.concat([
        _breakdowns(current, "CURRENT", "net_result_R"),
        breakdowns,
    ], ignore_index=True, sort=False).to_csv(output / "all_breakdowns.csv", index=False)

    special = special_candidate_matrix(audits=audit, trades=trades, outcomes=outcomes)
    special.to_csv(output / "special_near_miss_analysis.csv", index=False)

    leader, robust, neighbors = select_quality_leader(grid)
    neighbors.to_csv(output / "leader_neighbor_robustness.csv", index=False)
    leader_trades = trades.loc[trades.variant == leader.variant]
    recovered_leader = leader_trades.loc[leader_trades.recovered_vs_current]
    leader_recovered_metrics = _metric_row(recovered_leader, result_column="net_result_R")
    recommend = bool(
        leader.net_avg_R > 0
        and leader.net_profit_factor > 1.0
        and leader.net_max_drawdown_R <= current_net["max_drawdown_R"]
        and leader_recovered_metrics["avg_R"] > 0
        and leader_recovered_metrics["profit_factor"] > 1.0
        and robust
    )

    manifest = {
        "development_only": True,
        "window": {"start": str(prepared.start_timestamp), "end_exclusive": str(prepared.end_exclusive)},
        "bars": prepared.end_position - prepared.start_position,
        "forensic_csv_bug": True,
        "strategy_logic_bug": False,
        "cost_assumption": {"round_turn_usd": ROUND_TURN_COST_USD, "nq_usd_per_point": NQ_DOLLARS_PER_POINT},
        "current_gross": current_gross,
        "current_net": current_net,
        "quality_leader": leader.to_dict(),
        "robust_neighbors": robust,
        "recommend_freeze_for_new_oos": recommend,
        "special_ids": list(SPECIAL_IDS),
        "grid_cells": len(grid),
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest
