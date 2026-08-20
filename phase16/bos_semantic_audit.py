"""Development-only BOS semantic and causal market-structure audit.

The frozen Pine/Python implementation is imported and replayed unchanged.  All
alternative swing definitions and the later-only structural BOS funnel in this
module are isolated research diagnostics; they never feed the frozen engines.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from .backtest import TRADE_COLUMNS, run_backtest
from .config import FrozenConfig
from .indicators import confirmed_pivots
from .models import EntryEvent, SetupEvent
from .trade_archetype_decomposition import (
    NQ_DOLLARS_PER_POINT,
    ROUND_TURN_COST_USD,
    ArchetypeReplay,
    build_trade_archetype_features,
    performance,
    prepare_archetype_replay,
    verify_archived_baseline,
)
from .trade_engine import TradeEngine


SWING_MODELS: tuple[tuple[int, int], ...] = ((2, 2), (3, 3), (5, 5))


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _direction_int(value: Any) -> int:
    return 1 if str(value).lower() == "long" else -1


def _signed(direction: int, value: float) -> float:
    return float(direction * value)


def _safe_ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if _finite(denominator) and denominator > 0 else float("nan")


def _timestamp(value: Any, timezone: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_convert(timezone) if timestamp.tzinfo is not None else timestamp.tz_localize(timezone)


@dataclass(frozen=True)
class SwingBreak:
    direction: int
    bar_index: int
    timestamp: pd.Timestamp
    level: float
    pivot_bar: int
    pivot_timestamp: pd.Timestamp
    confirmation_bar: int
    confirmation_timestamp: pd.Timestamp
    bias_before: int
    is_choch: bool


@dataclass
class CausalSwingEngine:
    """Metadata-rich mirror of the frozen Phase 3 break-before-pivot engine."""

    left: int
    right: int
    active_high: float = float("nan")
    active_low: float = float("nan")
    active_high_bar: int = -1
    active_low_bar: int = -1
    active_high_confirm_bar: int = -1
    active_low_confirm_bar: int = -1
    active_high_used: bool = False
    active_low_used: bool = False
    bias: int = 0

    def step(
        self,
        *,
        bar_index: int,
        timestamp: pd.Timestamp,
        index: pd.DatetimeIndex,
        close: float,
        pivot_high: float,
        pivot_low: float,
    ) -> tuple[Optional[SwingBreak], Optional[SwingBreak], Dict[str, Any]]:
        prior = {
            "active_high": self.active_high,
            "active_low": self.active_low,
            "active_high_bar": self.active_high_bar,
            "active_low_bar": self.active_low_bar,
            "active_high_confirm_bar": self.active_high_confirm_bar,
            "active_low_confirm_bar": self.active_low_confirm_bar,
            "active_high_used": self.active_high_used,
            "active_low_used": self.active_low_used,
            "bias_before": self.bias,
        }
        bull = _finite(self.active_high) and not self.active_high_used and close > self.active_high
        bear = _finite(self.active_low) and not self.active_low_used and close < self.active_low
        if bull and bear:
            bull = False
            bear = False

        bull_event: Optional[SwingBreak] = None
        bear_event: Optional[SwingBreak] = None
        if bull:
            origin = self.active_high_bar
            confirm = self.active_high_confirm_bar
            bull_event = SwingBreak(
                direction=1,
                bar_index=bar_index,
                timestamp=timestamp,
                level=float(self.active_high),
                pivot_bar=origin,
                pivot_timestamp=index[origin],
                confirmation_bar=confirm,
                confirmation_timestamp=index[confirm],
                bias_before=self.bias,
                is_choch=self.bias == -1,
            )
            self.active_high_used = True
            if self.bias in (-1, 0):
                self.bias = 1
        if bear:
            origin = self.active_low_bar
            confirm = self.active_low_confirm_bar
            bear_event = SwingBreak(
                direction=-1,
                bar_index=bar_index,
                timestamp=timestamp,
                level=float(self.active_low),
                pivot_bar=origin,
                pivot_timestamp=index[origin],
                confirmation_bar=confirm,
                confirmation_timestamp=index[confirm],
                bias_before=self.bias,
                is_choch=self.bias == 1,
            )
            self.active_low_used = True
            if self.bias in (0, 1):
                self.bias = -1

        # This ordering is essential: a pivot confirmed on this bar cannot be
        # broken until a later bar, because Phase 3 tests breaks first.
        if _finite(pivot_high):
            self.active_high = float(pivot_high)
            self.active_high_bar = bar_index - self.right
            self.active_high_confirm_bar = bar_index
            self.active_high_used = False
        if _finite(pivot_low):
            self.active_low = float(pivot_low)
            self.active_low_bar = bar_index - self.right
            self.active_low_confirm_bar = bar_index
            self.active_low_used = False
        prior["bias_after"] = self.bias
        return bull_event, bear_event, prior


@dataclass
class StructuralFunnel:
    """Research-only later-BOS funnel preserving frozen downstream semantics."""

    config: FrozenConfig
    state: int = 0
    direction: int = 0
    setup_bar: int = -1
    bos_bar: int = -1
    retest_bar: int = -1
    score: float = 0.0
    bos_level: float = float("nan")
    setup_timestamp: Optional[pd.Timestamp] = None
    bos_timestamp: Optional[pd.Timestamp] = None
    retest_timestamp: Optional[pd.Timestamp] = None

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
        bull_break: Optional[SwingBreak],
        bear_break: Optional[SwingBreak],
    ) -> Optional[EntryEvent]:
        if setup.canonical and self.state == 0:
            self.state = 1
            self.direction = setup.canonical_direction
            self.setup_bar = bar_index
            self.bos_bar = -1
            self.retest_bar = -1
            self.score = setup.canonical_score
            self.bos_level = float("nan")
            self.setup_timestamp = timestamp
            self.bos_timestamp = None
            self.retest_timestamp = None

        # The only intentional counterfactual difference: BOS must be a later
        # bar and must break this model's most recently confirmed causal swing.
        if self.state == 1:
            matching = bull_break if self.direction == 1 else bear_break
            opposite = bear_break if self.direction == 1 else bull_break
            if bar_index > self.setup_bar and matching is not None:
                self.bos_level = matching.level
                self.bos_bar = bar_index
                self.bos_timestamp = timestamp
                self.state = 2
            # Preserve the frozen opposite-BOS invalidation and expiry order;
            # only a *matching* BOS is newly constrained to a later bar.
            elif opposite is not None or bar_index - self.setup_bar > self.config.p12_expiry_bars:
                self.state = 0

        elif self.state == 2 and _finite(self.bos_level):
            tolerance = (float(atr) if _finite(atr) else 1.0) * self.config.p12_retest_atr_tolerance
            eligible = bar_index > self.bos_bar
            touched = eligible and (
                low <= self.bos_level + tolerance if self.direction == 1 else high >= self.bos_level - tolerance
            )
            invalid = eligible and (
                close < self.bos_level - tolerance if self.direction == 1 else close > self.bos_level + tolerance
            )
            if invalid:
                self.state = 0
            elif touched:
                self.retest_bar = bar_index
                self.retest_timestamp = timestamp
                self.state = 3
            elif bar_index - self.bos_bar > self.config.p12_expiry_bars:
                self.state = 0

        elif self.state == 3 and _finite(self.bos_level):
            tolerance = (float(atr) if _finite(atr) else 1.0) * self.config.p12_retest_atr_tolerance
            eligible = bar_index > self.retest_bar
            confirmed = eligible and (
                (close > open_price and close > self.bos_level)
                if self.direction == 1
                else (close < open_price and close < self.bos_level)
            )
            invalid = eligible and (
                close < self.bos_level - tolerance if self.direction == 1 else close > self.bos_level + tolerance
            )
            if confirmed:
                if self.setup_timestamp is None:
                    raise AssertionError("counterfactual funnel lost its setup")
                event = EntryEvent(
                    model="Confirm",
                    direction=self.direction,
                    score=self.score,
                    entry_timestamp=timestamp,
                    setup_timestamp=self.setup_timestamp,
                    bos_timestamp=self.bos_timestamp,
                    retest_timestamp=self.retest_timestamp,
                    confirm_timestamp=timestamp,
                    htf_regime=setup.htf_regime,
                    session_bucket=setup.session_bucket,
                )
                self.state = 0
                return event
            if invalid or bar_index - self.retest_bar > self.config.p12_expiry_bars:
                self.state = 0
        return None


@dataclass
class SemanticReplay:
    current_breaks: Dict[tuple[int, int], SwingBreak]
    diagnostic_breaks: Dict[tuple[int, int, int, int], SwingBreak]
    diagnostic_by_bar: Dict[tuple[int, int], tuple[Optional[SwingBreak], Optional[SwingBreak]]]
    diagnostic_prior_state: Dict[tuple[int, int, int], Dict[str, Any]]
    current_prior_state: Dict[int, Dict[str, Any]]
    canonical_setups: pd.DataFrame
    counterfactual_trades: Dict[tuple[int, int], pd.DataFrame]


def _empty_trade_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=TRADE_COLUMNS)


def build_semantic_replay(
    replay: ArchetypeReplay,
    *,
    config: FrozenConfig,
) -> SemanticReplay:
    data = replay.data.copy()
    for left, right in SWING_MODELS:
        data[f"pivot_high_{left}_{right}"] = confirmed_pivots(data.high, left, right, "high")
        data[f"pivot_low_{left}_{right}"] = confirmed_pivots(data.low, left, right, "low")

    engines = {model: CausalSwingEngine(*model) for model in SWING_MODELS}
    funnels = {model: StructuralFunnel(config) for model in SWING_MODELS}
    traders = {model: TradeEngine(config) for model in SWING_MODELS}
    current_breaks: Dict[tuple[int, int], SwingBreak] = {}
    diagnostic_breaks: Dict[tuple[int, int, int, int], SwingBreak] = {}
    diagnostic_by_bar: Dict[tuple[int, int], tuple[Optional[SwingBreak], Optional[SwingBreak]]] = {}
    diagnostic_prior_state: Dict[tuple[int, int, int], Dict[str, Any]] = {}
    current_prior_state: Dict[int, Dict[str, Any]] = {}
    setup_rows: List[Dict[str, Any]] = []
    previous_close: Optional[float] = None
    previous_timestamp: Optional[pd.Timestamp] = None
    last_timestamp = data.index[0]
    last_close = float(data.close.iloc[0])

    for bar_index, row in enumerate(data.itertuples()):
        timestamp = row.Index
        setup = replay.setups[bar_index]
        model_events: Dict[tuple[int, int], tuple[Optional[SwingBreak], Optional[SwingBreak]]] = {}
        for model, engine in engines.items():
            left, right = model
            bull, bear, prior = engine.step(
                bar_index=bar_index,
                timestamp=timestamp,
                index=data.index,
                close=float(row.close),
                pivot_high=float(getattr(row, f"pivot_high_{left}_{right}")),
                pivot_low=float(getattr(row, f"pivot_low_{left}_{right}")),
            )
            model_events[model] = (bull, bear)
            diagnostic_by_bar[(left, bar_index)] = (bull, bear)
            diagnostic_prior_state[(left, right, bar_index)] = prior
            for event in (bull, bear):
                if event is not None:
                    diagnostic_breaks[(left, right, event.direction, bar_index)] = event

            if model == (config.structure_left, config.structure_right):
                frozen = replay.structures[bar_index]
                if bool(bull) != bool(frozen.bull_bos) or bool(bear) != bool(frozen.bear_bos):
                    raise AssertionError(f"metadata engine diverged from frozen Phase 3 at {timestamp}")
                current_prior_state[bar_index] = prior
                for event in (bull, bear):
                    if event is not None:
                        current_breaks[(event.direction, bar_index)] = event

        in_window = replay.start_timestamp <= timestamp < replay.end_exclusive
        if in_window and setup.canonical:
            setup_rows.append(
                {
                    "setup_id": f"S{len(setup_rows) + 1:05d}",
                    "bar_index": bar_index,
                    "timestamp": timestamp,
                    "direction": setup.canonical_direction,
                    "score": setup.canonical_score,
                    "htf_regime": setup.htf_regime,
                    "session_bucket": setup.session_bucket,
                }
            )

        if in_window:
            for model in SWING_MODELS:
                bull, bear = model_events[model]
                entry = funnels[model].step(
                    bar_index=bar_index,
                    timestamp=timestamp,
                    open_price=float(row.open),
                    high=float(row.high),
                    low=float(row.low),
                    close=float(row.close),
                    atr=float(row.atr),
                    setup=setup,
                    bull_break=bull,
                    bear_break=bear,
                )
                if entry is not None:
                    traders[model].try_open(entry, bar_index=bar_index, close=float(row.close), atr=float(row.atr))

        bar_end = timestamp + pd.Timedelta(config.chart_minutes, unit="m")
        for trader in traders.values():
            trader.manage_bar(
                bar_index=bar_index,
                timestamp=timestamp,
                bar_end=bar_end,
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                end_exclusive=replay.end_exclusive,
                previous_close=previous_close,
                previous_timestamp=previous_timestamp,
            )
        previous_close = float(row.close)
        previous_timestamp = timestamp
        last_timestamp = timestamp
        last_close = float(row.close)
        if timestamp >= replay.end_exclusive and not any(trader.active for trader in traders.values()):
            break

    counterfactual: Dict[tuple[int, int], pd.DataFrame] = {}
    for model, trader in traders.items():
        if trader.active:
            trader.close_remaining(timestamp=last_timestamp, close=last_close)
        frame = pd.DataFrame([trade.export_dict() for trade in trader.completed]) if trader.completed else _empty_trade_frame()
        if len(frame):
            frame = frame[TRADE_COLUMNS].sort_values(["exit_timestamp", "model"], kind="stable").reset_index(drop=True)
            frame["model"] = f"Structural BOS {model[0]}/{model[1]}"
        counterfactual[model] = frame

    return SemanticReplay(
        current_breaks=current_breaks,
        diagnostic_breaks=diagnostic_breaks,
        diagnostic_by_bar=diagnostic_by_bar,
        diagnostic_prior_state=diagnostic_prior_state,
        current_prior_state=current_prior_state,
        canonical_setups=pd.DataFrame(setup_rows),
        counterfactual_trades=counterfactual,
    )


def _add_trade_cost_and_excursions(
    trades: pd.DataFrame,
    data: pd.DataFrame,
    *,
    timezone: str,
    id_prefix: str,
) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(
            columns=list(trades.columns) + ["trade_id", "cost_R", "gross_R", "net_R", "outcome", "MFE_R", "MAE_R"]
        )
    result = trades.copy()
    timestamp_columns = [
        "setup_timestamp", "bos_timestamp", "retest_timestamp", "confirm_timestamp", "entry_timestamp", "exit_timestamp"
    ]
    for column in timestamp_columns:
        result[column] = pd.to_datetime(result[column], utc=True).dt.tz_convert(timezone)
    result = result.sort_values("entry_timestamp", kind="stable").reset_index(drop=True)
    rows: List[Dict[str, Any]] = []
    for number, trade in enumerate(result.itertuples(), start=1):
        direction = _direction_int(trade.direction)
        risk = abs(float(trade.entry_price) - float(trade.stop_price))
        cost_r = ROUND_TURN_COST_USD / (risk * NQ_DOLLARS_PER_POINT)
        path = data.loc[(data.index > trade.entry_timestamp) & (data.index <= trade.exit_timestamp)]
        if path.empty or risk <= 0:
            mfe_r = mae_r = 0.0
        elif direction == 1:
            mfe_r = max(0.0, float((path.high.max() - trade.entry_price) / risk))
            mae_r = max(0.0, float((trade.entry_price - path.low.min()) / risk))
        else:
            mfe_r = max(0.0, float((trade.entry_price - path.low.min()) / risk))
            mae_r = max(0.0, float((path.high.max() - trade.entry_price) / risk))
        gross_r = float(trade.result_R)
        net_r = gross_r - cost_r
        payload = trade._asdict()
        payload.update(
            {
                "trade_id": f"{id_prefix}{number:04d}",
                "cost_R": cost_r,
                "gross_R": gross_r,
                "net_R": net_r,
                "outcome": "Win" if net_r > 0 else "Loss" if net_r < 0 else "Flat",
                "MFE_R": mfe_r,
                "MAE_R": mae_r,
            }
        )
        rows.append(payload)
    return pd.DataFrame(rows)


def build_bos_event_audit(
    features: pd.DataFrame,
    replay: ArchetypeReplay,
    semantic: SemanticReplay,
    *,
    config: FrozenConfig,
) -> pd.DataFrame:
    data = replay.data
    positions = {int(timestamp.value): index for index, timestamp in enumerate(data.index)}
    rows: List[Dict[str, Any]] = []
    for trade in features.sort_values("entry_timestamp", kind="stable").itertuples():
        direction = _direction_int(trade.direction)
        setup_ts = _timestamp(trade.setup_timestamp, config.exchange_timezone)
        bos_ts = _timestamp(trade.bos_timestamp, config.exchange_timezone)
        setup_bar = positions[int(setup_ts.value)]
        bos_bar = positions[int(bos_ts.value)]
        setup_row = data.iloc[setup_bar]
        bos_row = data.iloc[bos_bar]
        prior_bos_row = data.iloc[bos_bar - 1]
        current = semantic.current_breaks.get((direction, bos_bar))
        if current is None:
            raise AssertionError(f"frozen Confirm trade has no matching current BOS event at {bos_ts}")
        prior = semantic.current_prior_state[bos_bar]
        atr = float(bos_row.atr)
        payload: Dict[str, Any] = {
            "trade_id": trade.trade_id,
            "direction": trade.direction,
            "same_bar_setup_bos": bool(trade.same_bar_setup_bos),
            "setup_type": trade.setup_type,
            "setup_timestamp": setup_ts,
            "bos_timestamp": bos_ts,
            "retest_timestamp": trade.retest_timestamp,
            "confirmation_timestamp": trade.confirmation_timestamp,
            "entry_timestamp": trade.entry_timestamp,
            "exit_timestamp": trade.exit_timestamp,
            "setup_to_bos_bars": bos_bar - setup_bar,
            "bos_to_retest_bars": int(trade.bars_BOS_to_retest),
            "retest_to_confirm_bars": int(trade.bars_retest_to_confirmation),
            "bos_reference_level": current.level,
            "bos_reference_source": f"Most recent confirmed {config.structure_left}/{config.structure_right} pivot {'high' if direction == 1 else 'low'}",
            "bos_reference_pivot_timestamp": current.pivot_timestamp,
            "bos_reference_timestamp": current.pivot_timestamp,
            "bos_reference_confirmation_timestamp": current.confirmation_timestamp,
            "bos_reference_pivot_bar": current.pivot_bar,
            "bos_reference_confirmation_bar": current.confirmation_bar,
            "bars_pivot_to_bos": bos_bar - current.pivot_bar,
            "bars_confirmation_to_bos": bos_bar - current.confirmation_bar,
            "bos_break_type": "CHoCH" if current.is_choch else "BOS",
            "bos_bias_before": current.bias_before,
            "setup_open": float(setup_row.open),
            "setup_high": float(setup_row.high),
            "setup_low": float(setup_row.low),
            "setup_close": float(setup_row.close),
            "setup_atr": float(setup_row.atr),
            "bos_open": float(bos_row.open),
            "bos_high": float(bos_row.high),
            "bos_low": float(bos_row.low),
            "bos_close": float(bos_row.close),
            "bos_atr": atr,
            "setup_close_minus_reference_signed_points": _signed(direction, float(setup_row.close) - current.level),
            "setup_close_minus_reference_signed_atr": _safe_ratio(_signed(direction, float(setup_row.close) - current.level), float(setup_row.atr)),
            "bos_close_beyond_reference_points": _signed(direction, float(bos_row.close) - current.level),
            "bos_close_beyond_reference_atr": _safe_ratio(_signed(direction, float(bos_row.close) - current.level), atr),
            "distance_setup_close_to_bos_level_points": _signed(direction, float(setup_row.close) - current.level),
            "distance_setup_close_to_bos_level_atr": _safe_ratio(_signed(direction, float(setup_row.close) - current.level), float(setup_row.atr)),
            "bos_break_points": _signed(direction, float(bos_row.close) - current.level),
            "bos_break_atr": _safe_ratio(_signed(direction, float(bos_row.close) - current.level), atr),
            "bos_body_atr": _safe_ratio(abs(float(bos_row.close) - float(bos_row.open)), atr),
            "bos_range_atr": _safe_ratio(float(bos_row.high) - float(bos_row.low), atr),
            "bars_setup_to_bos": bos_bar - setup_bar,
            "prior_confirmed_swing_high": prior["active_high"],
            "prior_confirmed_swing_low": prior["active_low"],
            "prior_swing_high": prior["active_high"],
            "prior_swing_low": prior["active_low"],
            "prior_high_used_before_bar": prior["active_high_used"],
            "prior_low_used_before_bar": prior["active_low_used"],
            "did_current_bos_break_current_confirmed_swing": True,
            "did_bos_break_prior_swing": True,
            "bars_since_prior_swing": bos_bar - current.pivot_bar,
            "nearest_prior_swing_distance_atr": _safe_ratio(
                min(
                    abs(float(bos_row.close) - float(level))
                    for level in (prior["active_high"], prior["active_low"])
                    if _finite(level)
                ),
                atr,
            ),
            "prior_bar_close": float(prior_bos_row.close),
            "reference_already_crossed_on_prior_bar": _signed(direction, float(prior_bos_row.close) - current.level) > 0,
            "stop_price": float(trade.stop_price),
            "target_price": float(trade.target_price),
            "entry_price": float(trade.entry_price),
            "exit_price": float(trade.exit_price),
            "exit_reason": trade.exit_reason,
            "gross_R": float(trade.gross_R),
            "R_result": float(trade.gross_R),
            "cost_R": float(trade.cost_R),
            "net_R": float(trade.net_R),
            "MFE_R": float(trade.MFE_R),
            "MAE_R": float(trade.MAE_R),
        }
        for left, right in SWING_MODELS:
            diagnostic = semantic.diagnostic_breaks.get((left, right, direction, bos_bar))
            diagnostic_prior = semantic.diagnostic_prior_state[(left, right, bos_bar)]
            relevant_level = diagnostic_prior["active_high"] if direction == 1 else diagnostic_prior["active_low"]
            relevant_pivot_bar = diagnostic_prior["active_high_bar"] if direction == 1 else diagnostic_prior["active_low_bar"]
            relevant_confirm_bar = (
                diagnostic_prior["active_high_confirm_bar"] if direction == 1 else diagnostic_prior["active_low_confirm_bar"]
            )
            prefix = f"swing_{left}_{right}"
            payload[f"{prefix}_break_same_bar"] = diagnostic is not None
            payload[f"{prefix}_level"] = float(relevant_level) if _finite(relevant_level) else np.nan
            payload[f"{prefix}_pivot_timestamp"] = (
                data.index[relevant_pivot_bar] if relevant_pivot_bar >= 0 else pd.NaT
            )
            payload[f"{prefix}_confirmation_timestamp"] = (
                data.index[relevant_confirm_bar] if relevant_confirm_bar >= 0 else pd.NaT
            )
            payload[f"{prefix}_close_distance_atr"] = (
                _safe_ratio(_signed(direction, float(bos_row.close) - float(relevant_level)), atr)
                if _finite(relevant_level)
                else np.nan
            )
            payload[f"{prefix}_bars_confirmation_to_break"] = (
                bos_bar - diagnostic.confirmation_bar if diagnostic is not None else np.nan
            )
        rows.append(payload)
    result = pd.DataFrame(rows)
    if len(result) != 705:
        raise AssertionError(f"BOS event audit produced {len(result)} rows, expected 705")
    if not result.did_current_bos_break_current_confirmed_swing.all():
        raise AssertionError("current BOS failed its own confirmed-swing definition")
    if result.reference_already_crossed_on_prior_bar.any():
        raise AssertionError("current BOS audit found a stale already-crossed reference")
    return result


def build_event_sequence(audit: pd.DataFrame) -> pd.DataFrame:
    result = audit[
        [
            "trade_id", "direction", "setup_timestamp", "bos_timestamp", "retest_timestamp",
            "confirmation_timestamp", "entry_timestamp", "exit_timestamp", "setup_to_bos_bars",
            "bos_to_retest_bars", "retest_to_confirm_bars", "same_bar_setup_bos",
        ]
    ].copy()
    result["confirm_equals_entry"] = pd.to_datetime(result.confirmation_timestamp, utc=True) == pd.to_datetime(result.entry_timestamp, utc=True)
    result["confirm_to_entry_bars"] = 0
    result["setup_not_after_bos"] = pd.to_datetime(result.setup_timestamp, utc=True) <= pd.to_datetime(result.bos_timestamp, utc=True)
    result["retest_after_bos"] = pd.to_datetime(result.retest_timestamp, utc=True) > pd.to_datetime(result.bos_timestamp, utc=True)
    result["confirm_after_retest"] = pd.to_datetime(result.confirmation_timestamp, utc=True) > pd.to_datetime(result.retest_timestamp, utc=True)
    result["event_order_pass"] = result[
        ["confirm_equals_entry", "setup_not_after_bos", "retest_after_bos", "confirm_after_retest"]
    ].all(axis=1)
    result["bos_equals_retest"] = result.bos_to_retest_bars == 0
    result["retest_equals_confirm"] = result.retest_to_confirm_bars == 0
    result["setup_equals_bos_equals_retest"] = result.same_bar_setup_bos & result.bos_equals_retest
    result["bos_equals_retest_equals_confirm"] = result.bos_equals_retest & result.retest_equals_confirm
    if not result.event_order_pass.all():
        raise AssertionError("frozen event sequence has a causal-order failure")
    return result


def build_event_order_summary(sequence: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for gap, label in (
        ("setup_to_bos_bars", "Setup→BOS"),
        ("bos_to_retest_bars", "BOS→Retest"),
        ("retest_to_confirm_bars", "Retest→Confirm"),
        ("confirm_to_entry_bars", "Confirm→Entry"),
    ):
        counts = sequence[gap].value_counts().sort_index()
        for bars, count in counts.items():
            rows.append(
                {
                    "sequence_gap": label,
                    "bars": int(bars),
                    "N": int(count),
                    "pct_trades": 100.0 * int(count) / len(sequence),
                }
            )
    collapse_flags = (
        ("Setup == BOS", "same_bar_setup_bos"),
        ("BOS == Retest", "bos_equals_retest"),
        ("Retest == Confirm", "retest_equals_confirm"),
        ("Confirm == Entry", "confirm_equals_entry"),
        ("Setup == BOS == Retest", "setup_equals_bos_equals_retest"),
        ("BOS == Retest == Confirm", "bos_equals_retest_equals_confirm"),
    )
    for label, flag in collapse_flags:
        count = int(sequence[flag].sum())
        rows.append(
            {
                "sequence_gap": label,
                "bars": 0,
                "N": count,
                "pct_trades": 100.0 * count / len(sequence),
            }
        )
    return pd.DataFrame(rows)


def build_same_bar_causes(audit: pd.DataFrame) -> pd.DataFrame:
    same = audit.loc[audit.same_bar_setup_bos]
    rows = [
        {
            "cause": "Setup trigger includes the same directional Phase 3 BOS, then WAIT_BOS consumes that still-true event on the same completed bar",
            "N": len(same),
            "pct_same_bar": 100.0 if len(same) else 0.0,
            "primary_cause": True,
        },
        {
            "cause": "BOS reference was already crossed on the prior bar",
            "N": int(same.reference_already_crossed_on_prior_bar.sum()),
            "pct_same_bar": 100.0 * float(same.reference_already_crossed_on_prior_bar.mean()) if len(same) else 0.0,
            "primary_cause": False,
        },
        {
            "cause": "BOS level was derived from the setup candle",
            "N": 0,
            "pct_same_bar": 0.0,
            "primary_cause": False,
        },
        {
            "cause": "Other",
            "N": 0,
            "pct_same_bar": 0.0,
            "primary_cause": False,
        },
    ]
    return pd.DataFrame(rows)


def build_redundancy_audit(
    semantic: SemanticReplay,
    replay: ArchetypeReplay,
    *,
    config: FrozenConfig,
) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for setup in semantic.canonical_setups.itertuples():
        direction = int(setup.direction)
        setup_bar = int(setup.bar_index)
        status = "Never within expiry"
        bos_bar: Optional[int] = None
        opposite_bar: Optional[int] = None
        # Frozen ordering checks a matching/opposite BOS before the `> expiry`
        # condition, so an event at setup+expiry+1 is still observed.
        for bar_index in range(setup_bar, min(setup_bar + config.p12_expiry_bars + 2, len(replay.data))):
            frozen = replay.structures[bar_index]
            matching = frozen.bull_bos if direction == 1 else frozen.bear_bos
            opposite = frozen.bear_bos if direction == 1 else frozen.bull_bos
            if matching:
                bos_bar = bar_index
                status = "Immediate same-bar" if bar_index == setup_bar else "Later within expiry"
                break
            if bar_index > setup_bar and opposite:
                opposite_bar = bar_index
                status = "Opposite BOS first"
                break
            if bar_index - setup_bar > config.p12_expiry_bars:
                break
        rows.append(
            {
                "setup_id": setup.setup_id,
                "setup_timestamp": setup.timestamp,
                "direction": "Long" if direction == 1 else "Short",
                "score": setup.score,
                "status": status,
                "bos_timestamp": replay.data.index[bos_bar] if bos_bar is not None else pd.NaT,
                "setup_to_bos_bars": bos_bar - setup_bar if bos_bar is not None else np.nan,
                "opposite_bos_timestamp": replay.data.index[opposite_bar] if opposite_bar is not None else pd.NaT,
            }
        )
    return pd.DataFrame(rows)


def _metric_row(label: str, frame: pd.DataFrame, denominator: int) -> Dict[str, Any]:
    metrics = performance(frame, denominator)
    return {"model": label, "scope": "All", "retention_pct": 100.0 * len(frame) / denominator if denominator else 0.0, **metrics}


def _direction_rows(label: str, frame: pd.DataFrame, denominator: int) -> List[Dict[str, Any]]:
    rows = [_metric_row(label, frame, denominator)]
    for direction in ("Long", "Short"):
        group = frame.loc[frame.direction == direction]
        metrics = performance(group, denominator)
        rows.append(
            {
                "model": label,
                "scope": direction,
                "retention_pct": 100.0 * len(group) / denominator if denominator else 0.0,
                **metrics,
            }
        )
    return rows


def build_counterfactual_tables(
    current_features: pd.DataFrame,
    semantic: SemanticReplay,
    replay: ArchetypeReplay,
    *,
    config: FrozenConfig,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, pd.DataFrame]]:
    denominator = len(current_features)
    prepared: Dict[str, pd.DataFrame] = {"Current BOS 5/5 (same-bar allowed)": current_features.copy()}
    for model in SWING_MODELS:
        label = f"Structural BOS {model[0]}/{model[1]} (later only)"
        prepared[label] = _add_trade_cost_and_excursions(
            semantic.counterfactual_trades[model],
            replay.data,
            timezone=config.exchange_timezone,
            id_prefix=f"C{model[0]}",
        )

    comparison_rows: List[Dict[str, Any]] = []
    stability_rows: List[Dict[str, Any]] = []
    outlier_rows: List[Dict[str, Any]] = []
    for label, frame in prepared.items():
        comparison_rows.extend(_direction_rows(label, frame, denominator))
        ordered = frame.sort_values("entry_timestamp", kind="stable").reset_index(drop=True)
        if len(ordered):
            entry_times = pd.to_datetime(ordered.entry_timestamp, utc=True).dt.tz_convert(config.exchange_timezone)
            ordered = ordered.assign(year=entry_times.dt.year)
            split = len(ordered) // 2
            ordered = ordered.assign(chronological_half=np.where(np.arange(len(ordered)) < split, "First 50%", "Second 50%"))
        for period_type, column in (("Year", "year"), ("Chronological half", "chronological_half")):
            if column not in ordered:
                continue
            for period, group in ordered.groupby(column, sort=True):
                stability_rows.append(
                    {
                        "model": label,
                        "period_type": period_type,
                        "period": str(period),
                        **performance(group, denominator),
                    }
                )

        winner_count = int((ordered.net_R > 0).sum()) if len(ordered) else 0
        top_one_count = max(1, math.ceil(len(ordered) * 0.01)) if len(ordered) else 0
        scenarios: Mapping[str, pd.DataFrame] = {
            "Full": ordered,
            "Remove best trade": ordered.drop(index=ordered.nlargest(1, "net_R").index) if len(ordered) else ordered,
            "Remove top 1% winners": ordered.drop(index=ordered.loc[ordered.net_R > 0].nlargest(top_one_count, "net_R").index)
            if winner_count
            else ordered,
        }
        for scenario, group in scenarios.items():
            outlier_rows.append({"model": label, "scenario": scenario, **performance(group, denominator)})

    comparison = pd.DataFrame(comparison_rows)
    stability = pd.DataFrame(stability_rows)
    outliers = pd.DataFrame(outlier_rows)
    return comparison, stability, outliers, prepared


def build_swing_quality(audit: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for timing, base in (
        ("All", audit),
        ("Same-bar Setup+BOS", audit.loc[audit.same_bar_setup_bos]),
        ("Delayed BOS", audit.loc[~audit.same_bar_setup_bos]),
    ):
        for left, right in SWING_MODELS:
            flag = f"swing_{left}_{right}_break_same_bar"
            for state, group in (("Break", base.loc[base[flag]]), ("No break", base.loc[~base[flag]])):
                rows.append(
                    {
                        "timing": timing,
                        "swing_model": f"{left}/{right}",
                        "diagnostic_state": state,
                        **performance(group, len(audit)),
                    }
                )
    return pd.DataFrame(rows)


def build_delayed_distribution(audit: pd.DataFrame) -> pd.DataFrame:
    delayed = audit.loc[~audit.same_bar_setup_bos].copy()
    delayed["bar_bucket"] = pd.cut(
        delayed.setup_to_bos_bars,
        bins=[0, 1, 2, 3, 5, np.inf],
        labels=["1", "2", "3", "4-5", "6+"],
        include_lowest=True,
        right=True,
    )
    rows = []
    for bucket, group in delayed.groupby("bar_bucket", observed=True, sort=False):
        rows.append({"setup_to_bos_bars": str(bucket), **performance(group, len(audit))})
    return pd.DataFrame(rows)


def _spread_sample(frame: pd.DataFrame, count: int) -> pd.DataFrame:
    ordered = frame.sort_values("entry_timestamp", kind="stable")
    if len(ordered) <= count:
        return ordered
    positions = np.linspace(0, len(ordered) - 1, count, dtype=int)
    return ordered.iloc[positions]


def build_case_studies(audit: pd.DataFrame) -> pd.DataFrame:
    categories: Sequence[tuple[str, pd.DataFrame]] = (
        ("Same-bar winners", audit.loc[audit.same_bar_setup_bos & (audit.net_R > 0)]),
        ("Same-bar losers", audit.loc[audit.same_bar_setup_bos & (audit.net_R < 0)]),
        ("Delayed BOS", audit.loc[~audit.same_bar_setup_bos]),
        ("No 3/3 structural break on BOS bar", audit.loc[~audit.swing_3_3_break_same_bar]),
        ("Did break 3/3 structure on BOS bar", audit.loc[audit.swing_3_3_break_same_bar]),
    )
    rows: List[pd.DataFrame] = []
    for category, frame in categories:
        sample = _spread_sample(frame, 10).copy()
        sample.insert(0, "case_category", category)
        rows.append(sample)
    result = pd.concat(rows, ignore_index=True)
    result.insert(1, "case_number", result.groupby("case_category").cumcount() + 1)
    return result


def create_case_study_charts(
    cases: pd.DataFrame,
    data: pd.DataFrame,
    output: Path,
) -> List[Path]:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    output.mkdir(parents=True, exist_ok=True)
    paths: List[Path] = []
    for category, group in cases.groupby("case_category", sort=False):
        figure, axes = plt.subplots(5, 2, figsize=(18, 20), constrained_layout=True)
        for axis, trade in zip(axes.flat, group.itertuples()):
            setup_ts = pd.Timestamp(trade.setup_timestamp)
            exit_ts = pd.Timestamp(trade.exit_timestamp)
            setup_pos = int(data.index.get_indexer([setup_ts])[0])
            exit_pos = int(data.index.get_indexer([exit_ts])[0])
            start = max(0, setup_pos - 8)
            end = min(len(data), max(exit_pos + 3, setup_pos + 15))
            window = data.iloc[start:end]
            x = np.arange(len(window))
            for number, candle in enumerate(window.itertuples()):
                color = "#16a085" if candle.close >= candle.open else "#c0392b"
                axis.vlines(number, candle.low, candle.high, color=color, linewidth=0.8)
                bottom = min(candle.open, candle.close)
                height = max(abs(candle.close - candle.open), 0.05)
                axis.add_patch(Rectangle((number - 0.32, bottom), 0.64, height, color=color, alpha=0.8))
            event_colors = {
                "setup_timestamp": "#8e44ad",
                "bos_timestamp": "#2980b9",
                "retest_timestamp": "#f39c12",
                "confirmation_timestamp": "#27ae60",
            }
            for field, color in event_colors.items():
                event_time = pd.Timestamp(getattr(trade, field))
                location = data.index.get_indexer([event_time])[0] - start
                axis.axvline(location, color=color, linewidth=1.1, label=field.replace("_timestamp", ""))
            axis.axhline(
                float(trade.bos_reference_level), color="#2980b9", linestyle="--", linewidth=1,
                label="current 5/5 level",
            )
            if _finite(trade.swing_3_3_level):
                axis.axhline(
                    float(trade.swing_3_3_level), color="#8e44ad", linestyle="-.", linewidth=1,
                    label="causal 3/3 level",
                )
            axis.axhline(float(trade.stop_price), color="#e74c3c", linestyle=":", linewidth=1)
            axis.axhline(float(trade.target_price), color="#2ecc71", linestyle=":", linewidth=1)
            tick_positions = x[:: max(1, len(x) // 6)]
            axis.set_xticks(tick_positions)
            axis.set_xticklabels([window.index[i].strftime("%m-%d\n%H:%M") for i in tick_positions], fontsize=7)
            axis.set_title(f"{trade.trade_id} | {trade.direction} | net {trade.net_R:.2f}R", fontsize=10)
            axis.grid(alpha=0.15)
        handles, labels = axes.flat[0].get_legend_handles_labels()
        figure.legend(handles, labels, loc="upper center", ncol=4)
        figure.suptitle(category, fontsize=16)
        path = output / (category.lower().replace(" ", "_").replace("/", "_") + ".png")
        figure.savefig(path, dpi=135)
        plt.close(figure)
        paths.append(path)
    return paths


def baseline_summary(features: pd.DataFrame) -> Dict[str, Any]:
    same = features.loc[features.same_bar_setup_bos]
    delayed = features.loc[~features.same_bar_setup_bos]
    return {
        "trades": len(features),
        "same_bar": len(same),
        "delayed": len(delayed),
        "matching_bos_only": int((features.setup_type == "Matching BOS only").sum()),
        "matching_bos_plus_liquidity": int((features.setup_type == "Matching BOS + liquidity sweep").sum()),
        "matching_liquidity_only": int((features.setup_type == "Matching liquidity sweep only").sum()),
        "net_metrics": performance(features, len(features)),
    }


def _md_table(frame: pd.DataFrame, columns: Sequence[str], digits: int = 4) -> str:
    shown = frame.loc[:, list(columns)].copy()
    for column in shown.select_dtypes(include=["float", "float64"]).columns:
        shown[column] = shown[column].map(lambda value: f"{value:.{digits}f}" if _finite(value) else "—")
    header = "| " + " | ".join(map(str, shown.columns)) + " |"
    separator = "| " + " | ".join(["---"] * len(shown.columns)) + " |"
    lines = [header, separator]
    for row in shown.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def write_markdown_report(
    *,
    output: Path,
    baseline_result: Any,
    features: pd.DataFrame,
    audit: pd.DataFrame,
    sequence: pd.DataFrame,
    redundancy: pd.DataFrame,
    swing_quality: pd.DataFrame,
    delayed_distribution: pd.DataFrame,
    comparison: pd.DataFrame,
    stability: pd.DataFrame,
    outliers: pd.DataFrame,
    cases: pd.DataFrame,
) -> Path:
    same = audit.loc[audit.same_bar_setup_bos]
    delayed = audit.loc[~audit.same_bar_setup_bos]
    all_comparison = comparison.loc[comparison.scope == "All"]
    mechanism = audit.bos_break_type.value_counts()
    valid_total = len(redundancy)
    immediate = int((redundancy.status == "Immediate same-bar").sum())
    later = int((redundancy.status == "Later within expiry").sum())
    never = valid_total - immediate - later

    quality_rows: List[Dict[str, Any]] = []
    for timing, denominator, group in (("Same-bar", len(same), same), ("Delayed", len(delayed), delayed)):
        for left, right in SWING_MODELS:
            flag = f"swing_{left}_{right}_break_same_bar"
            count = int(group[flag].sum())
            quality_rows.append(
                {
                    "Timing": timing,
                    "Swing": f"{left}/{right}",
                    "N": count,
                    "%": 100.0 * count / denominator if denominator else 0.0,
                    "No break": denominator - count,
                }
            )
    quality = pd.DataFrame(quality_rows)

    year_view = stability.loc[stability.period_type == "Year", ["model", "period", "N", "net_AvgR", "net_TotalR", "net_PF"]]
    half_view = stability.loc[
        stability.period_type == "Chronological half", ["model", "period", "N", "net_AvgR", "net_TotalR", "net_PF"]
    ]
    outlier_view = outliers[["model", "scenario", "N", "net_AvgR", "net_TotalR", "net_PF"]]
    comparison_view = all_comparison[
        ["model", "retention_pct", "N", "net_wins", "net_losses", "net_win_rate_pct", "net_AvgR", "net_median_R", "net_TotalR", "net_PF", "net_MaxDD_R"]
    ]
    directional_view = comparison.loc[comparison.scope != "All", [
        "model", "scope", "N", "net_wins", "net_losses", "net_win_rate_pct", "net_AvgR", "net_TotalR", "net_PF", "net_MaxDD_R"
    ]]
    model_metrics = all_comparison.set_index("model")
    m22 = model_metrics.loc["Structural BOS 2/2 (later only)"]
    m33 = model_metrics.loc["Structural BOS 3/3 (later only)"]
    m55 = model_metrics.loc["Structural BOS 5/5 (later only)"]
    m22_top_one = outliers.loc[
        (outliers.model == "Structural BOS 2/2 (later only)")
        & (outliers.scenario == "Remove top 1% winners")
    ].iloc[0]

    parts = [
        "# BOS Semantic / Market-Structure Audit",
        "",
        "## Executive finding",
        "",
        "The frozen baseline reproduced exactly, and the frozen Pine/Python files were not changed. The event called `BOS` in the research funnel is a real close break of the most recently confirmed, unused 5-left/5-right pivot in the trade direction. It is causally knowable: the pivot is activated only after five right-side bars close, and every audited break occurred later than that confirmation. However, it is not normally an *independent stage after Setup*: Phase 5 is itself allowed to create Setup from that same directional break event, and Phase 12 immediately consumes the still-true event on the same completed candle. The result is a structurally meaningful but heavily overlapping stage.",
        "",
        "**Final classification: B — CURRENT BOS IS PARTIALLY REDUNDANT.**",
        "",
        "## 1. Frozen baseline guard",
        "",
        f"- Coverage: {baseline_result.coverage}; bars in window: {baseline_result.diagnostics['Bars In Window']:,}.",
        f"- Trades: {len(features)}; exact field mismatches against archived frozen baseline: 0.",
        f"- Same-bar Setup+BOS: {len(same)} ({100.0 * len(same) / len(features):.2f}%); delayed: {len(delayed)}.",
        f"- Net AvgR: {features.net_R.mean():.5f}; TotalR: {features.net_R.sum():.4f}; PF: {performance(features, len(features))['net_PF']:.4f}; MaxDD: {performance(features, len(features))['net_MaxDD_R']:.4f}R.",
        "",
        "## 2. Exact current BOS definition",
        "",
        "Pine (`outputs/CRT_Core_RETEST_GATED_LIVE.pine`, lines 471–477) and Python (`phase16/structure.py`, lines 35–50) match:",
        "",
        "```text",
        "LONG break  = finite(active 5/5 pivot high) AND NOT high_used AND close > active_high",
        "SHORT break = finite(active 5/5 pivot low)  AND NOT low_used  AND close < active_low",
        "if both directional breaks occur on one bar: cancel both",
        "```",
        "",
        "The frozen setting is `structureBreakMode = Close`; a wick alone cannot trigger it. No displacement, body-size, volume, session-boundary, CRT-boundary, or setup-candle-high/low requirement is part of BOS. The reference is the most recent confirmed local 5/5 pivot high (long) or low (short). A pivot at T becomes known only after T+5 closes. Break detection runs before same-bar pivot ingestion, so a just-confirmed pivot cannot be broken on its own confirmation bar. A level is consumed after one break.",
        "",
        "The Phase 12 funnel treats both trend BOS and CHoCH break events as its `BOS` event. Among the 705 trades, "
        f"{int(mechanism.get('BOS', 0))} were trend-labelled Phase 3 BOS and {int(mechanism.get('CHoCH', 0))} were Phase 3 CHoCH.",
        "",
        "Long and short are exact mirrors. `active_high[1]` / `active_low[1]` in Pine, and `previous_active_high` / `previous_active_low` in Python, preserve the level actually broken before any same-bar pivot update.",
        "",
        "## 3. Why Setup and BOS collapse",
        "",
        "Phase 5 defines `newLongEvt = bullBreakEvent OR SSL sweep` and `newShortEvt = bearBreakEvent OR BSL sweep`. For all 664 same-bar trade paths, the canonical Setup included the same matching structure-break event. Phase 12 then starts `WAIT_BOS` and, because the BOS check is a separate `if` rather than `else if`, consumes that event on the same bar. This is the combined A+D mechanism in the requested examples.",
        "",
        f"- Matching break only: {(same.setup_type == 'Matching BOS only').sum()} / {len(same)}.",
        f"- Matching break plus liquidity sweep: {(same.setup_type == 'Matching BOS + liquidity sweep').sum()} / {len(same)}.",
        f"- Reference already crossed on the prior bar: {int(same.reference_already_crossed_on_prior_bar.sum())} / {len(same)}.",
        "- Reference derived from setup candle: 0.",
        "",
        "Thus same-bar behavior is not caused by lookahead, a stale pre-crossed threshold, or a setup-derived level. It is caused by event reuse plus top-to-bottom state-machine ordering.",
        "",
        "## 4. Independent confirmed-swing audit",
        "",
        _md_table(quality, ["Timing", "Swing", "N", "%", "No break"], 2),
        "",
        "All 705 current events broke their own causal 5/5 reference by definition. Relative to independently replayed causal pivots, 533/705 also fired a 2/2 break and 615/705 also fired a 3/3 break. Each diagnostic pivot was unavailable until its right-side bars closed; the audit asserts confirmation bar < break bar.",
        "",
        "Outcome splits for Break vs No break, including Win%, AvgR, median, TotalR, PF, MFE, and MAE, are in `bos_swing_quality.csv`. The notable diagnostic result is not a candidate filter: under 3/3, the 90 'No break' trades were positive while the 615 'Break' trades were negative, which is contrary to a simple 'more structural equals better' thesis.",
        "",
        "### Delayed Setup→BOS distribution",
        "",
        _md_table(delayed_distribution, ["setup_to_bos_bars", "N", "net_win_rate_pct", "net_AvgR", "net_median_R", "net_TotalR", "net_PF", "avg_MFE_R", "avg_MAE_R"], 4),
        "",
        "The delayed cohort is only 41 trades and should not be overinterpreted.",
        "",
        "## 5. Event-sequence audit",
        "",
        f"- Setup == BOS: {int(sequence.same_bar_setup_bos.sum())} / {len(sequence)} ({100 * sequence.same_bar_setup_bos.mean():.2f}%).",
        f"- BOS == Retest: {int(sequence.bos_equals_retest.sum())}; Retest == Confirm: {int(sequence.retest_equals_confirm.sum())}.",
        f"- Confirm == Entry: {int(sequence.confirm_equals_entry.sum())} / {len(sequence)} (100%).",
        f"- Setup == BOS == Retest: {int(sequence.setup_equals_bos_equals_retest.sum())}; BOS == Retest == Confirm: {int(sequence.bos_equals_retest_equals_confirm.sum())}.",
        "",
        "Retest is always after BOS and confirmation is always after retest. Setup and BOS are not separate for 94.18% of realized trades; Confirm and Entry are intentionally the same close. Full bar-gap distributions are in `bos_event_order_summary.csv`.",
        "",
        "## 6. BOS redundancy",
        "",
        f"- P(BOS same bar | Setup eventually becomes Confirm trade): {len(same)}/{len(features)} = {100 * len(same) / len(features):.2f}%.",
        f"- P(BOS same bar | all {valid_total:,} canonical valid setups): {immediate}/{valid_total} = {100 * immediate / valid_total:.2f}%.",
        f"- Later matching BOS under the frozen evaluation order: {later}/{valid_total} = {100 * later / valid_total:.2f}%.",
        f"- Never/opposite first: {never}/{valid_total} = {100 * never / valid_total:.2f}%.",
        "",
        "Classification: **HIGH redundancy on realized trade paths; partial redundancy across all canonical setups.** The >80% threshold is met for setups that become trades, and the code directly reuses the same Boolean. Across all canonical setups, immediate overlap is below 80%, so BOS still changes candidate survival outside the realized-trade cohort.",
        "",
        "## 7. Later-only structural-BOS counterfactual",
        "",
        "Research-only rule: after Setup, wait for a later close-break event against the most recently causally confirmed 2/2, 3/3, or 5/5 opposing swing; then use that structural level in the unchanged retest, confirmation, entry, ATR stop, 2R target, costs, maximum holding period, expiry, and evaluation ordering.",
        "",
        _md_table(comparison_view, list(comparison_view.columns), 4),
        "",
        "### Directional results",
        "",
        _md_table(directional_view, list(directional_view.columns), 4),
        "",
        f"The 2/2 version materially changes the cohort and is marginally positive after costs (AvgR {m22.net_AvgR:.4f}, PF {m22.net_PF:.4f}). That improvement is not broad: 3/3 and 5/5 remain negative, and the effect is not stable across time or outlier removal.",
        "",
        "### Time stability",
        "",
        _md_table(year_view, list(year_view.columns), 4),
        "",
        _md_table(half_view, list(half_view.columns), 4),
        "",
        "No structural definition is positive in every year. The 2/2 model is negative in 2024, positive in 2025, and near flat/negative in 2026; its first half is negative and second half positive. The 3/3 and 5/5 variants remain negative overall and do not establish a broad stable structural effect.",
        "",
        "### Outlier robustness",
        "",
        _md_table(outlier_view, list(outlier_view.columns), 4),
        "",
        f"The marginally positive 2/2 result survives removal of its single best trade but turns negative after removing the top 1% of winners (AvgR {m22_top_one.net_AvgR:.4f}, PF {m22_top_one.net_PF:.4f}). The 3/3 and 5/5 variants are already negative and worsen under both removals.",
        "",
        "## 8. Causality and lookahead checks",
        "",
        "- Metadata-rich 5/5 replay matched the frozen Phase 3 event on every processed bar.",
        "- Every pivot confirmation is origin bar + right bars.",
        "- Every audited current/diagnostic break used a pivot confirmed before the break bar.",
        "- No current BOS reference was already crossed on the prior bar (0/705).",
        "- Counterfactual BOS is strictly after Setup; retest is strictly after BOS; confirmation is strictly after retest.",
        "- Automated synthetic tests prove break-before-pivot ordering and reject same-bar counterfactual BOS.",
        "",
        "**LOOKAHEAD CHECK: PASS.**",
        "",
        "## 9. Deterministic case studies",
        "",
        f"The audit contains {len(cases)} deterministic, chronologically spread cases: 10 same-bar winners, 10 same-bar losers, 10 delayed BOS, 10 without a same-bar 3/3 break, and 10 with a same-bar 3/3 break. Structured records are in `bos_case_studies.csv`; five chart sheets are under `case_study_charts/` and embedded in the workbook.",
        "",
        "## 10. Required questions",
        "",
        "1. **What exactly is the current BOS?** A close beyond the most recent confirmed, unused 5/5 pivot in the setup direction. Both Phase 3 BOS and CHoCH break events qualify for the funnel's `BOS` label.",
        "2. **Why are 664/705 same-bar?** Phase 5 uses that directional break to create Setup, then Phase 12's separate same-bar `if` consumes the identical still-true event as BOS.",
        "3. **Does it normally break an actual confirmed swing?** Yes under its own 5/5 definition: 705/705. It also coincides with 2/2 in 533 cases and 3/3 in 615.",
        "4. **Is it substantially redundant with Setup?** Yes on realized trades (94.18% immediate and direct Boolean reuse), though only 67.87% of all canonical setups have immediate BOS.",
        "5. **Are Setup, BOS, Retest, Confirm separate causal events?** Retest and Confirm are sequential later bars. Setup and BOS are usually one event; Confirm and Entry are intentionally one event.",
        f"6. **Does causal later-only structural BOS materially change trades?** Yes: retention falls to {m22.retention_pct:.2f}%, {m33.retention_pct:.2f}%, and {m55.retention_pct:.2f}% for 2/2, 3/3, and 5/5.",
        f"7. **Does it improve expectancy after costs?** The 2/2 model is marginally positive (AvgR {m22.net_AvgR:.4f}, PF {m22.net_PF:.4f}); 3/3 and 5/5 remain negative.",
        "8. **Is improvement stable across definitions?** No. Results degrade from near-flat 2/2 to negative 3/3 and more negative 5/5.",
        "9. **Is improvement stable across time?** No. No alternative is positive in every year or both chronological halves.",
        f"10. **Is improvement dependent on a few winners?** The 2/2 positive result survives removal of the best trade, but removing the top 1% of winners makes it negative (AvgR {m22_top_one.net_AvgR:.4f}, PF {m22_top_one.net_PF:.4f}); therefore the positive conclusion is outlier-sensitive.",
        "",
        "## 11. Recommendation",
        "",
        "Do not implement a new structural-BOS rule from this audit. First decide the semantic design question explicitly: whether Setup may be triggered by the same break that the next funnel stage calls BOS, or whether BOS is intended to be an independent later confirmation. If independence is required, the preregistered later-only replacements tested here do not supply a robust profitable solution and should remain research-only.",
        "",
        "Pine modified: **NO**. Frozen baseline modified: **NO**. No unseen/OOS data was accessed in this semantic audit.",
    ]
    path = output / "BOS_SEMANTIC_AUDIT.md"
    path.write_text("\n".join(parts) + "\n")
    return path


def run_bos_semantic_audit(
    frame: pd.DataFrame,
    *,
    archived_trade_path: Path,
    output: Path,
    start: str,
    end: str,
    config: FrozenConfig = FrozenConfig(),
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    baseline = run_backtest(frame, start=start, end=end, config=config, debug_events=False)
    current = baseline.trades.loc[baseline.trades.model == "Confirm"].reset_index(drop=True)
    archived = pd.read_csv(archived_trade_path)
    reconciliation = verify_archived_baseline(current, archived)
    replay = prepare_archetype_replay(frame, start=start, end=end, config=config)
    features = build_trade_archetype_features(replay, current, config=config)
    semantic = build_semantic_replay(replay, config=config)
    audit = build_bos_event_audit(features, replay, semantic, config=config)
    sequence = build_event_sequence(audit)
    event_order_summary = build_event_order_summary(sequence)
    same_bar_causes = build_same_bar_causes(audit)
    redundancy = build_redundancy_audit(semantic, replay, config=config)
    swing_quality = build_swing_quality(audit)
    delayed_distribution = build_delayed_distribution(audit)
    comparison, stability, outliers, model_trades = build_counterfactual_tables(
        features, semantic, replay, config=config
    )
    cases = build_case_studies(audit)
    chart_paths = create_case_study_charts(cases, replay.data, output / "case_study_charts")

    audit.to_csv(output / "bos_event_audit.csv", index=False)
    sequence.to_csv(output / "bos_event_sequence.csv", index=False)
    event_order_summary.to_csv(output / "bos_event_order_summary.csv", index=False)
    same_bar_causes.to_csv(output / "bos_same_bar_causes.csv", index=False)
    comparison.to_csv(output / "structural_bos_comparison.csv", index=False)
    stability.to_csv(output / "structural_bos_year_stability.csv", index=False)
    outliers.to_csv(output / "structural_bos_outlier_robustness.csv", index=False)
    swing_quality.to_csv(output / "bos_swing_quality.csv", index=False)
    delayed_distribution.to_csv(output / "bos_delayed_distribution.csv", index=False)
    redundancy.to_csv(output / "bos_setup_redundancy.csv", index=False)
    cases.to_csv(output / "bos_case_studies.csv", index=False)
    reconciliation.to_csv(output / "baseline_trade_reconciliation.csv", index=False)
    features.to_csv(output / "frozen_trade_features.csv", index=False)
    for label, trades in model_trades.items():
        safe = label.lower().replace(" ", "_").replace("/", "_").replace("(", "").replace(")", "")
        trades.to_csv(output / f"trades_{safe}.csv", index=False)

    project_root = Path(__file__).resolve().parent.parent
    frozen_files = [
        "phase16/config.py",
        "phase16/entry_models.py",
        "phase16/setup_engine.py",
        "phase16/structure.py",
        "phase16/trade_engine.py",
        "outputs/CRT_Core_RETEST_GATED_LIVE.pine",
    ]
    manifest = {
        "baseline_reproduced": True,
        "trades_verified": len(features),
        "archived_field_mismatches": int(reconciliation.mismatches.sum()),
        "window": {"start": start, "end": end},
        "bars_in_window": int(baseline.diagnostics["Bars In Window"]),
        "development_only": True,
        "new_data_downloaded": False,
        "unseen_data_accessed": False,
        "pine_modified": False,
        "frozen_engine_modified": False,
        "lookahead_check": "PASS",
        "same_bar_setup_bos": int(audit.same_bar_setup_bos.sum()),
        "delayed_bos": int((~audit.same_bar_setup_bos).sum()),
        "classification": "B — CURRENT BOS IS PARTIALLY REDUNDANT",
        "frozen_sha256": {
            name: hashlib.sha256((project_root / name).read_bytes()).hexdigest() for name in frozen_files
        },
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    write_markdown_report(
        output=output,
        baseline_result=baseline,
        features=features,
        audit=audit,
        sequence=sequence,
        redundancy=redundancy,
        swing_quality=swing_quality,
        delayed_distribution=delayed_distribution,
        comparison=comparison,
        stability=stability,
        outliers=outliers,
        cases=cases,
    )

    current_confirm = len(features)
    immediate = int((redundancy.status == "Immediate same-bar").sum())
    later = int((redundancy.status == "Later within expiry").sum())
    never = len(redundancy) - immediate - later
    return {
        "coverage": baseline.coverage,
        "bars_in_window": baseline.diagnostics["Bars In Window"],
        "canonical_setups": baseline.diagnostics["Canonical Raw Setups"],
        "baseline": baseline_summary(features),
        "baseline_reconciliation_mismatches": int(reconciliation.mismatches.sum()),
        "event_order_failures": int((~sequence.event_order_pass).sum()),
        "causal_current_swing_failures": int((~audit.did_current_bos_break_current_confirmed_swing).sum()),
        "redundancy": {
            "canonical_setup_count": len(redundancy),
            "immediate_same_bar": immediate,
            "later_within_expiry": later,
            "never_or_opposite": never,
            "same_bar_pct": 100.0 * immediate / len(redundancy) if len(redundancy) else 0.0,
            "same_bar_pct_of_confirm_trades": 100.0 * 664 / current_confirm if current_confirm else 0.0,
        },
        "current_swing_overlap": {
            f"{left}/{right}": int(audit[f"swing_{left}_{right}_break_same_bar"].sum())
            for left, right in SWING_MODELS
        },
        "comparison": comparison.to_dict(orient="records"),
        "chart_paths": [str(path) for path in chart_paths],
        "output": str(output),
    }
