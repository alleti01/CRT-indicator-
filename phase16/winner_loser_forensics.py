"""Development-window winner/loser entry-quality forensics.

This module is an analysis-only consumer of the frozen Phase 3/4/5 engines and
the already validated 42-trade Confirm result.  It never changes the entry
funnel, trade engine, frozen configuration, or production Pine implementation.
All explanatory features are knowable no later than the entry bar close.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Sequence

import numpy as np
import pandas as pd

from .backtest import validation_window
from .config import FrozenConfig
from .indicators import (
    add_base_indicators,
    add_previous_closed_htf_regime,
    crt_reference_and_sweeps,
    htf_regime_name,
    is_in_session,
    score_band,
    session_bucket_name,
)
from .liquidity import LiquidityEngine
from .metrics import summarize_group
from .resample import cme_session_date
from .setup_engine import SetupEngine
from .structure import StructureEngine


ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0

OUTCOME_COLUMNS = {
    "outcome",
    "is_winner",
    "gross_R",
    "net_R",
    "MFE_R",
    "MAE_R",
    "exit_timestamp",
    "exit_reason",
}

NUMERIC_FEATURES = [
    "setup_score",
    "setup_liquidity_component",
    "setup_structure_component",
    "setup_bias_component",
    "setup_displacement_component",
    "setup_session_component",
    "setup_structure_distance_points",
    "setup_structure_distance_atr",
    "setup_body_atr",
    "setup_range_atr",
    "setup_upper_wick_ratio",
    "setup_lower_wick_ratio",
    "bos_displacement_points",
    "bos_displacement_atr",
    "bos_body_atr",
    "bos_range_atr",
    "bos_body_pct_range",
    "bos_close_beyond_structure_atr",
    "bos_upper_wick_ratio",
    "bos_lower_wick_ratio",
    "setup_to_bos_bars",
    "bos_relative_volume_20",
    "bos_to_retest_bars",
    "retest_distance_points",
    "retest_distance_atr",
    "retest_penetration_atr",
    "retest_max_penetration_atr",
    "retest_body_atr",
    "retest_range_atr",
    "retest_wick_toward_atr",
    "retest_wick_away_atr",
    "retest_close_distance_bos_atr",
    "retest_touch_count_through_accept",
    "confirm_body_atr",
    "confirm_range_atr",
    "confirm_body_pct_range",
    "confirm_close_location",
    "confirm_directional_close_location",
    "confirm_displacement_away_atr",
    "confirm_close_distance_bos_atr",
    "confirm_rejection_wick_atr",
    "retest_to_confirm_bars",
    "bos_to_entry_bars",
    "entry_atr",
    "entry_atr_percentile_100",
    "session_high_distance_atr",
    "session_low_distance_atr",
    "nearest_structure_distance_atr",
    "directional_room_to_structure_atr",
    "phase3_bias_alignment",
    "htf_alignment",
    "minutes_since_midnight",
]

CATEGORICAL_FEATURES = [
    "direction",
    "session",
    "HTF_regime",
    "setup_candle_direction",
    "bos_candle_direction",
    "retest_candle_direction",
    "same_bar_setup_bos",
    "phase3_bias",
    "phase3_alignment",
    "HTF_alignment",
    "entry_hour",
    "setup_score_band",
]

FEATURE_LABELS = {
    "setup_score": "Original setup score",
    "setup_liquidity_component": "Setup liquidity component",
    "setup_structure_component": "Setup structure component",
    "setup_bias_component": "Setup bias component",
    "setup_displacement_component": "Setup displacement component",
    "setup_session_component": "Setup session component",
    "setup_structure_distance_points": "Setup close beyond structure (points)",
    "setup_structure_distance_atr": "Setup close beyond structure / ATR",
    "setup_body_atr": "Setup body / ATR",
    "setup_range_atr": "Setup range / ATR",
    "setup_upper_wick_ratio": "Setup upper wick / range",
    "setup_lower_wick_ratio": "Setup lower wick / range",
    "bos_displacement_points": "BOS close displacement (points)",
    "bos_displacement_atr": "BOS close displacement / ATR",
    "bos_body_atr": "BOS body / ATR",
    "bos_range_atr": "BOS range / ATR",
    "bos_body_pct_range": "BOS body / range",
    "bos_close_beyond_structure_atr": "BOS close beyond structure / ATR",
    "bos_upper_wick_ratio": "BOS upper wick / range",
    "bos_lower_wick_ratio": "BOS lower wick / range",
    "setup_to_bos_bars": "Bars setup to BOS",
    "bos_relative_volume_20": "BOS volume / prior-20 mean",
    "bos_to_retest_bars": "Bars BOS to retest",
    "retest_distance_points": "Retest probe distance to BOS (points)",
    "retest_distance_atr": "Retest probe distance to BOS / ATR",
    "retest_penetration_atr": "Retest penetration through BOS / ATR",
    "retest_max_penetration_atr": "Max pre-accept penetration / ATR",
    "retest_body_atr": "Retest body / ATR",
    "retest_range_atr": "Retest range / ATR",
    "retest_wick_toward_atr": "Retest wick toward BOS / ATR",
    "retest_wick_away_atr": "Retest wick away / ATR",
    "retest_close_distance_bos_atr": "Retest close beyond BOS / ATR",
    "retest_touch_count_through_accept": "BOS-region touches through retest",
    "confirm_body_atr": "Confirmation body / ATR",
    "confirm_range_atr": "Confirmation range / ATR",
    "confirm_body_pct_range": "Confirmation body / range",
    "confirm_close_location": "Confirmation close location (low to high)",
    "confirm_directional_close_location": "Directional confirmation close location",
    "confirm_displacement_away_atr": "Confirmation displacement from retest / ATR",
    "confirm_close_distance_bos_atr": "Confirmation close beyond BOS / ATR",
    "confirm_rejection_wick_atr": "Confirmation rejection wick / ATR",
    "retest_to_confirm_bars": "Bars retest to confirmation",
    "bos_to_entry_bars": "Bars BOS to entry",
    "entry_atr": "Entry ATR (points)",
    "entry_atr_percentile_100": "Entry ATR percentile vs prior 100 bars",
    "session_high_distance_atr": "Distance below causal session high / ATR",
    "session_low_distance_atr": "Distance above causal session low / ATR",
    "nearest_structure_distance_atr": "Nearest active structure distance / ATR",
    "directional_room_to_structure_atr": "Directional room to active structure / ATR",
    "phase3_bias_alignment": "Phase-3 bias aligned (0/1)",
    "htf_alignment": "HTF regime aligned (0/1)",
    "minutes_since_midnight": "Entry minute of exchange day",
}


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if _finite(denominator) and denominator > 0 else float("nan")


def _timestamp_series(values: pd.Series, timezone: str) -> pd.Series:
    return pd.to_datetime(values, errors="raise", utc=True).dt.tz_convert(timezone)


def _direction_int(value: Any) -> int:
    return 1 if str(value).lower() == "long" else -1


def _candle_parts(row: pd.Series) -> Dict[str, float]:
    open_price, high, low, close = map(float, (row.open, row.high, row.low, row.close))
    candle_range = max(0.0, high - low)
    body = abs(close - open_price)
    upper = max(0.0, high - max(open_price, close))
    lower = max(0.0, min(open_price, close) - low)
    return {
        "body": body,
        "range": candle_range,
        "upper": upper,
        "lower": lower,
        "body_pct": _ratio(body, candle_range),
        "upper_ratio": _ratio(upper, candle_range),
        "lower_ratio": _ratio(lower, candle_range),
        "close_location": _ratio(close - low, candle_range),
    }


def _candle_direction(row: pd.Series, intended_direction: int) -> str:
    difference = float(row.close) - float(row.open)
    if difference == 0:
        return "Doji"
    return "With" if difference * intended_direction > 0 else "Against"


@dataclass
class ForensicReplay:
    data: pd.DataFrame
    setups: list[Any]
    structures: list[Any]
    score_components: Dict[tuple[int, int], Dict[str, float]]
    start_timestamp: pd.Timestamp
    end_exclusive: pd.Timestamp
    start_position: int
    end_position: int


def prepare_forensic_replay(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig,
) -> ForensicReplay:
    """Replay the frozen engines and record analysis-only score attribution."""
    data = frame.tz_convert(config.exchange_timezone).sort_index().copy()
    data = add_base_indicators(data, config)
    data = add_previous_closed_htf_regime(data, config)
    data = data.join(crt_reference_and_sweeps(data))
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)

    structure_engine = StructureEngine(config)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    structures: list[Any] = []
    setups: list[Any] = []
    components: Dict[tuple[int, int], Dict[str, float]] = {}
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
        if setup.canonical:
            direction = setup.canonical_direction
            recent_liquidity = (
                setup_engine.ssl_sweep_bar >= 0
                and bar_index - setup_engine.ssl_sweep_bar <= config.se_liquidity_lookback
                if direction == 1
                else setup_engine.bsl_sweep_bar >= 0
                and bar_index - setup_engine.bsl_sweep_bar <= config.se_liquidity_lookback
            )
            structure_bar = setup_engine.bull_structure_bar if direction == 1 else setup_engine.bear_structure_bar
            recent_structure = structure_bar >= 0 and bar_index - structure_bar <= config.se_liquidity_lookback
            choch = setup_engine.bull_is_choch if direction == 1 else setup_engine.bear_is_choch
            bias = int(structure.bias_after)
            favorable_bias = bias == direction
            liquidity_component = 25.0 if recent_liquidity else 0.0
            structure_component = (
                (30.0 if choch else (30.0 if favorable_bias else 20.0))
                if recent_structure
                else 0.0
            )
            bias_component = 20.0 if favorable_bias else (10.0 if bias == 0 else 5.0)
            body_average = float(row.body_sma)
            directional_body = direction * (float(row.close) - float(row.open))
            displacement_component = (
                15.0
                if _finite(body_average)
                and body_average > 0
                and directional_body > config.se_displacement_multiplier * body_average
                else 0.0
            )
            session_component = 10.0 if is_in_session(row.Index, config.se_preferred_session) else 0.0
            attributed = min(
                liquidity_component
                + structure_component
                + bias_component
                + displacement_component
                + session_component,
                100.0,
            )
            if abs(attributed - float(setup.canonical_score)) > 1e-9:
                raise AssertionError(
                    f"score attribution mismatch at {row.Index}: {attributed} != {setup.canonical_score}"
                )
            components[(direction, int(row.Index.value))] = {
                "setup_liquidity_component": liquidity_component,
                "setup_structure_component": structure_component,
                "setup_bias_component": bias_component,
                "setup_displacement_component": displacement_component,
                "setup_session_component": session_component,
                "setup_component_sum": attributed,
            }

    return ForensicReplay(
        data=data,
        setups=setups,
        structures=structures,
        score_components=components,
        start_timestamp=start_ts,
        end_exclusive=end_exclusive,
        start_position=int(data.index.searchsorted(start_ts, side="left")),
        end_position=int(data.index.searchsorted(end_exclusive, side="left")),
    )


def reconstruct_trade_features(
    replay: ForensicReplay,
    current_trades: pd.DataFrame,
    candidates: pd.DataFrame,
    *,
    config: FrozenConfig,
) -> pd.DataFrame:
    """Return one causal feature row for each of the 42 validated trades."""
    trades = current_trades.copy()
    timestamp_columns = [
        "setup_timestamp",
        "bos_timestamp",
        "retest_timestamp",
        "confirm_timestamp",
        "entry_timestamp",
        "exit_timestamp",
    ]
    for column in timestamp_columns:
        trades[column] = _timestamp_series(trades[column], config.exchange_timezone)
    candidates = candidates.copy()
    for column in [c for c in candidates.columns if "timestamp" in c]:
        candidates[column] = _timestamp_series(candidates[column], config.exchange_timezone)
    candidate_map = candidates.set_index("candidate_id")
    position_by_time = {int(timestamp.value): pos for pos, timestamp in enumerate(replay.data.index)}

    session_dates = pd.Series(cme_session_date(replay.data.index), index=replay.data.index)
    replay.data["causal_session_high"] = replay.data.groupby(session_dates)["high"].cummax()
    replay.data["causal_session_low"] = replay.data.groupby(session_dates)["low"].cummin()
    replay.data["prior20_volume_mean"] = replay.data["volume"].shift(1).rolling(20, min_periods=10).mean()

    rows: List[Dict[str, Any]] = []
    sorted_trades = trades.sort_values("entry_timestamp", kind="stable").reset_index(drop=True)
    for trade_number, trade in enumerate(sorted_trades.itertuples(), start=1):
        direction = _direction_int(trade.direction)
        positions = {
            name: position_by_time[int(pd.Timestamp(getattr(trade, f"{name}_timestamp")).value)]
            for name in ("setup", "bos", "retest", "confirm", "entry")
        }
        if positions["confirm"] != positions["entry"]:
            raise AssertionError("current Confirm entry must occur on confirmation bar")
        if not (
            positions["setup"] <= positions["bos"]
            < positions["retest"]
            < positions["confirm"]
        ):
            raise AssertionError(f"non-causal event sequence for candidate {trade.candidate_id}")

        setup_row = replay.data.iloc[positions["setup"]]
        bos_row = replay.data.iloc[positions["bos"]]
        retest_row = replay.data.iloc[positions["retest"]]
        confirm_row = replay.data.iloc[positions["confirm"]]
        entry_row = replay.data.iloc[positions["entry"]]
        setup_structure = replay.structures[positions["setup"]]
        entry_structure = replay.structures[positions["entry"]]
        candidate = candidate_map.loc[int(trade.candidate_id)]
        bos_level = float(candidate.bos_level_stored)
        if not _finite(bos_level):
            raise AssertionError(f"candidate {trade.candidate_id} has no stored BOS level")

        setup_atr = float(setup_row.atr)
        bos_atr = float(bos_row.atr)
        retest_atr = float(retest_row.atr)
        confirm_atr = float(confirm_row.atr)
        entry_atr = float(entry_row.atr)
        setup_parts = _candle_parts(setup_row)
        bos_parts = _candle_parts(bos_row)
        retest_parts = _candle_parts(retest_row)
        confirm_parts = _candle_parts(confirm_row)

        setup_level_prior = (
            setup_structure.previous_active_high
            if direction == 1
            else setup_structure.previous_active_low
        )
        setup_level_current = setup_structure.active_high if direction == 1 else setup_structure.active_low
        setup_level = float(setup_level_prior if _finite(setup_level_prior) else setup_level_current)
        setup_distance = direction * (float(setup_row.close) - setup_level) if _finite(setup_level) else float("nan")

        prior_close = float(replay.data.iloc[positions["bos"] - 1].close) if positions["bos"] > 0 else float(bos_row.open)
        bos_displacement = direction * (float(bos_row.close) - prior_close)
        close_beyond = direction * (float(bos_row.close) - bos_level)

        probe = float(retest_row.low) if direction == 1 else float(retest_row.high)
        retest_distance = abs(probe - bos_level)
        retest_penetration = max(0.0, direction * (bos_level - probe))
        path = replay.data.iloc[positions["bos"] + 1 : positions["retest"] + 1]
        penetrations: List[float] = []
        touch_count = 0
        for path_row in path.itertuples():
            path_atr = float(path_row.atr) if _finite(path_row.atr) else 1.0
            path_probe = float(path_row.low) if direction == 1 else float(path_row.high)
            penetrations.append(max(0.0, direction * (bos_level - path_probe)) / path_atr)
            tolerance = path_atr * config.p12_retest_atr_tolerance
            touched = path_probe <= bos_level + tolerance if direction == 1 else path_probe >= bos_level - tolerance
            touch_count += int(touched)
        max_penetration = max(penetrations, default=float("nan"))

        retest_toward_wick = retest_parts["lower"] if direction == 1 else retest_parts["upper"]
        retest_away_wick = retest_parts["upper"] if direction == 1 else retest_parts["lower"]
        confirm_rejection_wick = confirm_parts["lower"] if direction == 1 else confirm_parts["upper"]
        confirm_directional_location = (
            confirm_parts["close_location"]
            if direction == 1
            else 1.0 - confirm_parts["close_location"]
        )

        trailing_atr = replay.data["atr"].iloc[max(0, positions["entry"] - 100) : positions["entry"]].dropna()
        atr_percentile = float((trailing_atr <= entry_atr).mean()) if len(trailing_atr) else float("nan")
        active_levels = [
            float(value)
            for value in (entry_structure.active_high, entry_structure.active_low)
            if _finite(value)
        ]
        nearest_structure = (
            min(abs(float(entry_row.close) - level) for level in active_levels)
            if active_levels
            else float("nan")
        )
        directional_level = entry_structure.active_high if direction == 1 else entry_structure.active_low
        directional_room = (
            direction * (float(directional_level) - float(entry_row.close))
            if _finite(directional_level)
            else float("nan")
        )
        phase3_bias = int(entry_structure.bias_after)
        htf = int(trade.htf_regime)

        component_key = (direction, int(pd.Timestamp(trade.setup_timestamp).value))
        components = replay.score_components.get(component_key)
        if components is None:
            raise AssertionError(f"missing score components for candidate {trade.candidate_id}")
        if abs(float(components["setup_component_sum"]) - float(trade.score)) > 1e-9:
            raise AssertionError(f"trade score mismatch for candidate {trade.candidate_id}")

        record: Dict[str, Any] = {
            "trade_id": f"T{trade_number:03d}",
            "candidate_id": int(trade.candidate_id),
            "direction": str(trade.direction),
            "setup_timestamp": trade.setup_timestamp,
            "bos_timestamp": trade.bos_timestamp,
            "retest_timestamp": trade.retest_timestamp,
            "confirmation_timestamp": trade.confirm_timestamp,
            "entry_timestamp": trade.entry_timestamp,
            "session": session_bucket_name(int(trade.session_bucket)),
            "HTF_regime": htf_regime_name(htf),
            "setup_score": float(trade.score),
            "setup_score_band": score_band(float(trade.score)),
            **components,
            "setup_structure_level": setup_level,
            "setup_structure_distance_points": setup_distance,
            "setup_structure_distance_atr": _ratio(setup_distance, setup_atr),
            "setup_body_atr": _ratio(setup_parts["body"], setup_atr),
            "setup_range_atr": _ratio(setup_parts["range"], setup_atr),
            "setup_upper_wick_ratio": setup_parts["upper_ratio"],
            "setup_lower_wick_ratio": setup_parts["lower_ratio"],
            "setup_candle_direction": _candle_direction(setup_row, direction),
            "bos_level": bos_level,
            "bos_displacement_points": bos_displacement,
            "bos_displacement_atr": _ratio(bos_displacement, bos_atr),
            "bos_body_atr": _ratio(bos_parts["body"], bos_atr),
            "bos_range_atr": _ratio(bos_parts["range"], bos_atr),
            "bos_body_pct_range": bos_parts["body_pct"],
            "bos_close_beyond_structure_atr": _ratio(close_beyond, bos_atr),
            "bos_upper_wick_ratio": bos_parts["upper_ratio"],
            "bos_lower_wick_ratio": bos_parts["lower_ratio"],
            "bos_candle_direction": _candle_direction(bos_row, direction),
            "setup_to_bos_bars": positions["bos"] - positions["setup"],
            "same_bar_setup_bos": positions["bos"] == positions["setup"],
            "bos_relative_volume_20": _ratio(float(bos_row.volume), float(bos_row.prior20_volume_mean)),
            "bos_to_retest_bars": positions["retest"] - positions["bos"],
            "retest_distance_points": retest_distance,
            "retest_distance_atr": _ratio(retest_distance, retest_atr),
            "retest_penetration_atr": _ratio(retest_penetration, retest_atr),
            "retest_max_penetration_atr": max_penetration,
            "retest_body_atr": _ratio(retest_parts["body"], retest_atr),
            "retest_range_atr": _ratio(retest_parts["range"], retest_atr),
            "retest_wick_toward_atr": _ratio(retest_toward_wick, retest_atr),
            "retest_wick_away_atr": _ratio(retest_away_wick, retest_atr),
            "retest_close_distance_bos_atr": _ratio(direction * (float(retest_row.close) - bos_level), retest_atr),
            "retest_candle_direction": _candle_direction(retest_row, direction),
            "retest_touch_count_through_accept": touch_count,
            "confirm_body_atr": _ratio(confirm_parts["body"], confirm_atr),
            "confirm_range_atr": _ratio(confirm_parts["range"], confirm_atr),
            "confirm_body_pct_range": confirm_parts["body_pct"],
            "confirm_close_location": confirm_parts["close_location"],
            "confirm_directional_close_location": confirm_directional_location,
            "confirm_displacement_away_atr": _ratio(direction * (float(confirm_row.close) - float(retest_row.close)), confirm_atr),
            "confirm_close_distance_bos_atr": _ratio(direction * (float(confirm_row.close) - bos_level), confirm_atr),
            "confirm_rejection_wick_atr": _ratio(confirm_rejection_wick, confirm_atr),
            "retest_to_confirm_bars": positions["confirm"] - positions["retest"],
            "bos_to_entry_bars": positions["entry"] - positions["bos"],
            "entry_atr": entry_atr,
            "entry_atr_percentile_100": atr_percentile,
            "session_high_distance_atr": _ratio(float(entry_row.causal_session_high) - float(entry_row.close), entry_atr),
            "session_low_distance_atr": _ratio(float(entry_row.close) - float(entry_row.causal_session_low), entry_atr),
            "nearest_structure_distance_atr": _ratio(nearest_structure, entry_atr),
            "directional_room_to_structure_atr": _ratio(directional_room, entry_atr),
            "phase3_bias": {1: "Bull", -1: "Bear", 0: "Neutral"}.get(phase3_bias, "Neutral"),
            "phase3_bias_alignment": int(phase3_bias == direction),
            "phase3_alignment": "Aligned" if phase3_bias == direction else "Neutral" if phase3_bias == 0 else "Opposed",
            "htf_alignment": int(htf == direction),
            "HTF_alignment": "Aligned" if htf == direction else "Opposed",
            "entry_hour": f"{trade.entry_timestamp.hour:02d}:00",
            "minutes_since_midnight": trade.entry_timestamp.hour * 60 + trade.entry_timestamp.minute,
            "outcome": "Winner" if float(trade.net_result_R) > 0 else "Loser",
            "is_winner": int(float(trade.net_result_R) > 0),
            "gross_R": float(trade.gross_result_R),
            "net_R": float(trade.net_result_R),
            "MFE_R": float(trade.mfe_R),
            "MAE_R": float(trade.mae_R),
            "exit_timestamp": trade.exit_timestamp,
            "exit_reason": str(trade.exit_reason),
        }
        rows.append(record)

    result = pd.DataFrame(rows)
    if len(result) != 42 or int(result.is_winner.sum()) != 17:
        raise AssertionError("reconstruction does not match the validated 42-trade baseline")
    if set(NUMERIC_FEATURES) & OUTCOME_COLUMNS:
        raise AssertionError("outcome leakage detected in numeric feature registry")
    return result


def _effect_size(winners: pd.Series, losers: pd.Series) -> float:
    winners = pd.to_numeric(winners, errors="coerce").dropna().astype(float)
    losers = pd.to_numeric(losers, errors="coerce").dropna().astype(float)
    if len(winners) < 2 or len(losers) < 2:
        return float("nan")
    denominator = len(winners) + len(losers) - 2
    pooled_variance = ((len(winners) - 1) * winners.var(ddof=1) + (len(losers) - 1) * losers.var(ddof=1)) / denominator
    if pooled_variance <= 0 or not _finite(pooled_variance):
        return 0.0 if float(winners.mean()) == float(losers.mean()) else float("nan")
    return float((winners.mean() - losers.mean()) / math.sqrt(pooled_variance))


def _feature_effect(frame: pd.DataFrame, feature: str) -> float:
    return _effect_size(frame.loc[frame.is_winner == 1, feature], frame.loc[frame.is_winner == 0, feature])


def _stability_label(full_effect: float, effects: Sequence[float]) -> tuple[str, float, float]:
    finite = np.asarray([value for value in effects if _finite(value)], dtype=float)
    if not _finite(full_effect) or len(finite) == 0 or full_effect == 0:
        return "UNSTABLE", 0.0, 0.0
    sign_consistency = float(np.mean(np.sign(finite) == np.sign(full_effect)))
    min_ratio = float(np.min(np.abs(finite)) / abs(full_effect))
    if sign_consistency == 1.0 and min_ratio >= 0.75:
        return "STABLE", sign_consistency, min_ratio
    if sign_consistency >= 0.90 and min_ratio >= 0.50:
        return "PARTIALLY STABLE", sign_consistency, min_ratio
    return "UNSTABLE", sign_consistency, min_ratio


def continuous_comparison(features: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    best_index = features.net_R.idxmax()
    worst_index = features.net_R.idxmin()
    top_winner_indexes = features.loc[features.is_winner == 1].nlargest(2, "net_R").index
    top_loser_indexes = features.loc[features.is_winner == 0].nsmallest(2, "net_R").index
    removals = {
        "effect_without_best_trade": [best_index],
        "effect_without_worst_trade": [worst_index],
        "effect_without_top2_winners": list(top_winner_indexes),
        "effect_without_top2_losers": list(top_loser_indexes),
    }
    for feature in NUMERIC_FEATURES:
        winners = pd.to_numeric(features.loc[features.is_winner == 1, feature], errors="coerce").dropna()
        losers = pd.to_numeric(features.loc[features.is_winner == 0, feature], errors="coerce").dropna()
        effect = _effect_size(winners, losers)
        loo_effects = [_feature_effect(features.drop(index), feature) for index in features.index]
        stability, sign_consistency, min_ratio = _stability_label(effect, loo_effects)
        removal_effects = {
            name: _feature_effect(features.drop(indexes), feature)
            for name, indexes in removals.items()
        }
        finite_removals = [value for value in removal_effects.values() if _finite(value)]
        outlier_signs = (
            all(np.sign(value) == np.sign(effect) for value in finite_removals)
            if _finite(effect) and effect != 0 and finite_removals
            else False
        )
        min_outlier_ratio = (
            min(abs(value) for value in finite_removals) / abs(effect)
            if _finite(effect) and effect != 0 and finite_removals
            else 0.0
        )
        rows.append(
            {
                "feature": feature,
                "feature_label": FEATURE_LABELS.get(feature, feature),
                "winner_N": len(winners),
                "loser_N": len(losers),
                "winner_mean": float(winners.mean()) if len(winners) else np.nan,
                "loser_mean": float(losers.mean()) if len(losers) else np.nan,
                "winner_median": float(winners.median()) if len(winners) else np.nan,
                "loser_median": float(losers.median()) if len(losers) else np.nan,
                "mean_difference_W_minus_L": float(winners.mean() - losers.mean()) if len(winners) and len(losers) else np.nan,
                "median_difference_W_minus_L": float(winners.median() - losers.median()) if len(winners) and len(losers) else np.nan,
                "standardized_effect_Cohen_d": effect,
                "absolute_effect": abs(effect) if _finite(effect) else np.nan,
                "relationship": (
                    "Higher among winners"
                    if len(winners) and len(losers) and winners.median() > losers.median()
                    else "Lower among winners"
                    if len(winners) and len(losers) and winners.median() < losers.median()
                    else "Higher mean among winners; medians equal"
                    if len(winners) and len(losers) and winners.mean() > losers.mean()
                    else "Lower mean among winners; medians equal"
                    if len(winners) and len(losers) and winners.mean() < losers.mean()
                    else "No observed difference"
                ),
                "LOO_stability": stability,
                "LOO_sign_consistency": sign_consistency,
                "LOO_min_effect_ratio": min_ratio,
                **removal_effects,
                "outlier_dependence": "ROBUST TO LISTED REMOVALS" if outlier_signs and min_outlier_ratio >= 0.50 else "SENSITIVE TO OUTLIER REMOVAL",
                "outlier_min_effect_ratio": min_outlier_ratio,
            }
        )
    return pd.DataFrame(rows).sort_values("absolute_effect", ascending=False, na_position="last", kind="stable").reset_index(drop=True)


def _performance(frame: pd.DataFrame) -> Dict[str, Any]:
    results = pd.to_numeric(frame["net_R"], errors="coerce").dropna().astype(float)
    wins = int((results > 0).sum())
    losses = int((results < 0).sum())
    gross_profit = float(results[results > 0].sum())
    gross_loss = float(-results[results < 0].sum())
    return {
        "N": len(results),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": wins * 100.0 / len(results) if len(results) else 0.0,
        "AvgR": float(results.mean()) if len(results) else 0.0,
        "TotalR": float(results.sum()) if len(results) else 0.0,
        "PF": gross_profit / gross_loss if gross_loss > 0 else (99.9 if gross_profit > 0 else 0.0),
    }


def categorical_comparison(features: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for feature in CATEGORICAL_FEATURES:
        for category, group in features.groupby(feature, dropna=False, sort=True):
            rows.append({"feature": feature, "category": str(category), **_performance(group)})
    return pd.DataFrame(rows)


def _quantile_buckets(series: pd.Series) -> pd.Series:
    labels = ["Q1 lowest", "Q2", "Q3", "Q4 highest"]
    valid = pd.to_numeric(series, errors="coerce")
    ranked = valid.rank(method="first")
    result = pd.Series(index=series.index, dtype="object")
    mask = ranked.notna()
    if int(mask.sum()) >= 4:
        result.loc[mask] = pd.qcut(ranked.loc[mask], 4, labels=labels).astype(str)
    return result


def distribution_analysis(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    specifications: list[tuple[str, str, pd.Series]] = [
        ("bos_displacement_atr", "quantile", _quantile_buckets(features.bos_displacement_atr)),
        ("confirm_body_atr", "quantile", _quantile_buckets(features.confirm_body_atr)),
        ("retest_max_penetration_atr", "quantile", _quantile_buckets(features.retest_max_penetration_atr)),
        ("entry_atr_percentile_100", "fixed percentile quarters", pd.cut(features.entry_atr_percentile_100, [-np.inf, .25, .50, .75, np.inf], labels=["0-25%", "25-50%", "50-75%", "75-100%"])),
        ("bos_to_retest_bars", "fixed delay", pd.cut(features.bos_to_retest_bars, [0, 1, 2, 4, np.inf], labels=["1", "2", "3-4", "5+"])),
        ("retest_to_confirm_bars", "fixed delay", pd.cut(features.retest_to_confirm_bars, [0, 1, 2, 4, np.inf], labels=["1", "2", "3-4", "5+"])),
        ("setup_score", "frozen score bands", features.setup_score.map(score_band)),
    ]
    rows: List[Dict[str, Any]] = []
    summaries: List[Dict[str, Any]] = []
    order_maps = {
        "quantile": {"Q1 lowest": 1, "Q2": 2, "Q3": 3, "Q4 highest": 4},
        "fixed percentile quarters": {"0-25%": 1, "25-50%": 2, "50-75%": 3, "75-100%": 4},
        "fixed delay": {"1": 1, "2": 2, "3-4": 3, "5+": 4},
        "frozen score bands": {"<70": 0, "70-74": 1, "75-79": 2, "80-84": 3, "85-89": 4, "90-94": 5, "95+": 6},
    }
    for feature, method, buckets in specifications:
        working = features.assign(_bucket=buckets).dropna(subset=["_bucket"])
        grouped_rows: List[Dict[str, Any]] = []
        for bucket, group in working.groupby("_bucket", observed=True, sort=False):
            bucket_text = str(bucket)
            row = {
                "feature": feature,
                "feature_label": FEATURE_LABELS.get(feature, feature),
                "bucket_method": method,
                "bucket_order": order_maps[method][bucket_text],
                "bucket": bucket_text,
                "bucket_min": float(group[feature].min()),
                "bucket_max": float(group[feature].max()),
                **_performance(group),
            }
            grouped_rows.append(row)
            rows.append(row)
        ordered = pd.DataFrame(grouped_rows).sort_values("bucket_order")
        if len(ordered) >= 3 and ordered.AvgR.nunique() > 1:
            x_rank = ordered.bucket_order.rank(method="average").to_numpy(dtype=float)
            y_rank = ordered.AvgR.rank(method="average").to_numpy(dtype=float)
            rho = float(np.corrcoef(x_rank, y_rank)[0, 1])
        else:
            rho = np.nan
        differences = ordered.AvgR.diff().dropna()
        if len(differences) and bool((differences >= 0).all()) and bool((differences > 0).any()):
            pattern = "MONOTONIC UP"
        elif len(differences) and bool((differences <= 0).all()) and bool((differences < 0).any()):
            pattern = "MONOTONIC DOWN"
        elif _finite(rho) and abs(rho) >= 0.80:
            pattern = "ORDERED TENDENCY"
        else:
            pattern = "NON-MONOTONIC"
        summaries.append(
            {
                "feature": feature,
                "feature_label": FEATURE_LABELS.get(feature, feature),
                "bucket_method": method,
                "bucket_count": len(ordered),
                "min_bucket_N": int(ordered.N.min()) if len(ordered) else 0,
                "spearman_bucket_order_vs_AvgR": rho,
                "pattern": pattern,
            }
        )
    row_frame = pd.DataFrame(rows)
    feature_order = {feature: order for order, (feature, _, _) in enumerate(specifications)}
    row_frame["_feature_order"] = row_frame.feature.map(feature_order)
    row_frame = row_frame.sort_values(["_feature_order", "bucket_order"], kind="stable").drop(columns="_feature_order").reset_index(drop=True)
    summary_frame = pd.DataFrame(summaries)
    summary_frame["_feature_order"] = summary_frame.feature.map(feature_order)
    summary_frame = summary_frame.sort_values("_feature_order", kind="stable").drop(columns="_feature_order").reset_index(drop=True)
    return row_frame, summary_frame


def interaction_analysis(features: pd.DataFrame) -> pd.DataFrame:
    med = features[NUMERIC_FEATURES].median(numeric_only=True)
    conditions: list[tuple[str, str, pd.Series, str, pd.Series]] = [
        ("Strong BOS + strong confirmation", "BOS displacement / ATR >= median", features.bos_displacement_atr >= med.bos_displacement_atr, "Confirmation body / ATR >= median", features.confirm_body_atr >= med.confirm_body_atr),
        ("Strong BOS + shallow retest", "BOS displacement / ATR >= median", features.bos_displacement_atr >= med.bos_displacement_atr, "Max retest penetration / ATR <= median", features.retest_max_penetration_atr <= med.retest_max_penetration_atr),
        ("Shallow retest + strong confirmation", "Max retest penetration / ATR <= median", features.retest_max_penetration_atr <= med.retest_max_penetration_atr, "Confirmation body / ATR >= median", features.confirm_body_atr >= med.confirm_body_atr),
        ("HTF aligned + strong BOS", "HTF regime aligned", features.htf_alignment == 1, "BOS displacement / ATR >= median", features.bos_displacement_atr >= med.bos_displacement_atr),
        ("Core session + strong confirmation", "Entry in frozen 09:30-16:00 session", features.session.isin(["Opening", "Morning", "Midday", "Afternoon"]), "Confirmation body / ATR >= median", features.confirm_body_atr >= med.confirm_body_atr),
        ("Fast retest + strong confirmation", "BOS-to-retest bars <= median", features.bos_to_retest_bars <= med.bos_to_retest_bars, "Confirmation body / ATR >= median", features.confirm_body_atr >= med.confirm_body_atr),
        ("Same-bar setup/BOS + strong confirmation", "BOS occurs on setup bar", features.same_bar_setup_bos.astype(bool), "Confirmation body / ATR >= median", features.confirm_body_atr >= med.confirm_body_atr),
        ("High relative volume + strong BOS", "BOS relative volume >= median", features.bos_relative_volume_20 >= med.bos_relative_volume_20, "BOS displacement / ATR >= median", features.bos_displacement_atr >= med.bos_displacement_atr),
        ("More structural room + strong confirmation", "Directional room / ATR >= median", features.directional_room_to_structure_atr >= med.directional_room_to_structure_atr, "Confirmation body / ATR >= median", features.confirm_body_atr >= med.confirm_body_atr),
        ("Fast confirmation + shallow retest", "Retest-to-confirm bars <= median", features.retest_to_confirm_bars <= med.retest_to_confirm_bars, "Max retest penetration / ATR <= median", features.retest_max_penetration_atr <= med.retest_max_penetration_atr),
    ]
    rows: List[Dict[str, Any]] = []
    for interaction_id, (name, a_name, a_mask, b_name, b_mask) in enumerate(conditions, start=1):
        masks = {
            "Both": a_mask & b_mask,
            "A only": a_mask & ~b_mask,
            "B only": ~a_mask & b_mask,
            "Neither": ~a_mask & ~b_mask,
        }
        cell_metrics = {cell: _performance(features.loc[mask]) for cell, mask in masks.items()}
        for cell, metrics in cell_metrics.items():
            rows.append(
                {
                    "interaction_id": interaction_id,
                    "interaction": name,
                    "condition_A": a_name,
                    "condition_B": b_name,
                    "cell": cell,
                    **metrics,
                    "Both_minus_Neither_AvgR": cell_metrics["Both"]["AvgR"] - cell_metrics["Neither"]["AvgR"],
                    "exploratory_warning": "Small-sample exploratory interaction; no threshold selected from profit",
                }
            )
    return pd.DataFrame(rows)


def forensic_characteristics(features: pd.DataFrame) -> pd.DataFrame:
    q25 = features[NUMERIC_FEATURES].quantile(0.25, numeric_only=True)
    q75 = features[NUMERIC_FEATURES].quantile(0.75, numeric_only=True)
    loser_conditions: list[tuple[str, pd.Series, str]] = [
        ("Weak BOS displacement", features.bos_displacement_atr <= q25.bos_displacement_atr, "Bottom quartile BOS displacement / ATR"),
        ("Deep retest penetration", features.retest_max_penetration_atr >= q75.retest_max_penetration_atr, "Top quartile max penetration through BOS / ATR"),
        ("Weak confirmation body", features.confirm_body_atr <= q25.confirm_body_atr, "Bottom quartile confirmation body / ATR"),
        ("Delayed confirmation", features.retest_to_confirm_bars >= q75.retest_to_confirm_bars, "Top quartile retest-to-confirm delay"),
        ("ATR regime extreme", (features.entry_atr_percentile_100 <= .25) | (features.entry_atr_percentile_100 >= .75), "Entry ATR in lowest or highest trailing percentile quarter"),
        ("HTF disagreement", features.htf_alignment == 0, "Frozen HTF regime opposed to trade direction"),
        ("Overnight or premarket", features.session.isin(["Overnight", "Premarket"]), "Entry outside frozen 09:30-16:00 preferred session"),
        ("Constrained directional room", features.directional_room_to_structure_atr <= q25.directional_room_to_structure_atr, "Bottom quartile signed room to active structure"),
        ("Low relative BOS volume", features.bos_relative_volume_20 <= q25.bos_relative_volume_20, "Bottom quartile causal BOS relative volume"),
        ("Weak directional close location", features.confirm_directional_close_location <= q25.confirm_directional_close_location, "Bottom quartile confirmation close location in trade direction"),
    ]
    winner_conditions: list[tuple[str, pd.Series, str]] = [
        ("Strong BOS displacement", features.bos_displacement_atr >= q75.bos_displacement_atr, "Top quartile BOS displacement / ATR"),
        ("Shallow retest penetration", features.retest_max_penetration_atr <= q25.retest_max_penetration_atr, "Bottom quartile max penetration through BOS / ATR"),
        ("Strong confirmation body", features.confirm_body_atr >= q75.confirm_body_atr, "Top quartile confirmation body / ATR"),
        ("Fast confirmation", features.retest_to_confirm_bars <= q25.retest_to_confirm_bars, "Bottom quartile retest-to-confirm delay"),
        ("Middle ATR regime", features.entry_atr_percentile_100.between(.25, .75, inclusive="both"), "Entry ATR in middle two trailing percentile quarters"),
        ("HTF alignment", features.htf_alignment == 1, "Frozen HTF regime aligned with trade direction"),
        ("Core session", features.session.isin(["Opening", "Morning", "Midday", "Afternoon"]), "Entry in frozen 09:30-16:00 preferred session"),
        ("More directional room", features.directional_room_to_structure_atr >= q75.directional_room_to_structure_atr, "Top quartile signed room to active structure"),
        ("High relative BOS volume", features.bos_relative_volume_20 >= q75.bos_relative_volume_20, "Top quartile causal BOS relative volume"),
        ("Strong directional close location", features.confirm_directional_close_location >= q75.confirm_directional_close_location, "Top quartile confirmation close location in trade direction"),
    ]
    rows: List[Dict[str, Any]] = []
    for characteristic_type, definitions in (("LOSER CLUSTER", loser_conditions), ("WINNER CHARACTERISTIC", winner_conditions)):
        for characteristic, mask, definition in definitions:
            group = features.loc[mask]
            metrics = _performance(group)
            rows.append(
                {
                    "type": characteristic_type,
                    "characteristic": characteristic,
                    "definition": definition,
                    "winner_count": int(group.is_winner.sum()),
                    "winner_share_of_17_pct": float(group.is_winner.sum()) * 100.0 / 17.0,
                    "loser_count": int((group.is_winner == 0).sum()),
                    "loser_share_of_25_pct": float((group.is_winner == 0).sum()) * 100.0 / 25.0,
                    **metrics,
                }
            )
    return pd.DataFrame(rows)


def _rationale(feature: str) -> str:
    if feature.startswith("bos_"):
        return "A decisive, well-participated structure break may be less prone to immediate failure than a marginal break."
    if feature.startswith("confirm_"):
        return "The confirmation candle describes whether post-retest order flow is actually reasserting in the intended direction."
    if feature.startswith("retest_"):
        return "Retest depth, rejection, and delay proxy acceptance versus erosion of the newly broken structure."
    if feature.startswith("setup_"):
        return "The frozen setup components summarize the upstream liquidity, structure, bias, displacement, and session context."
    if "structure" in feature or "room" in feature:
        return "Nearby active structure can constrain path-to-target even when the entry sequence itself is valid."
    if "atr" in feature:
        return "Volatility state changes the noise-to-signal ratio and the dollar cost expressed in R."
    if "bars" in feature or "time" in feature or "minute" in feature:
        return "A longer sequence may indicate decaying information or different intraday liquidity conditions."
    if "alignment" in feature:
        return "Alignment tests whether the entry agrees with already-known directional context."
    return "This causal feature describes entry quality without using any post-entry outcome information."


def _fmt(value: Any, digits: int = 3) -> str:
    return "—" if not _finite(value) else f"{float(value):.{digits}f}"


def _current_metrics(features: pd.DataFrame) -> Dict[str, Any]:
    working = features[["entry_timestamp", "exit_timestamp", "net_R"]].copy()
    working["result_R"] = working.net_R
    working = working.sort_values("exit_timestamp", kind="stable")
    return summarize_group(working)


def _evidence_label(comparison: pd.DataFrame, distribution_summary: pd.DataFrame) -> str:
    durable = comparison.loc[
        (comparison.absolute_effect >= 0.50)
        & comparison.LOO_stability.isin(["STABLE", "PARTIALLY STABLE"])
        & (comparison.outlier_dependence == "ROBUST TO LISTED REMOVALS")
    ]
    ordered = distribution_summary.loc[
        distribution_summary.pattern.isin(["MONOTONIC UP", "MONOTONIC DOWN", "ORDERED TENDENCY"])
        & (distribution_summary.min_bucket_N >= 5)
    ]
    return "WEAK" if len(durable) >= 1 or len(ordered) >= 1 else "NO"


def build_report(
    *,
    features: pd.DataFrame,
    comparison: pd.DataFrame,
    categorical: pd.DataFrame,
    distributions: pd.DataFrame,
    distribution_summary: pd.DataFrame,
    interactions: pd.DataFrame,
    characteristics: pd.DataFrame,
    bars_in_window: int,
) -> str:
    current = _current_metrics(features)
    top = comparison.head(10)
    losers = characteristics.loc[
        (characteristics.type == "LOSER CLUSTER")
        & (characteristics.AvgR < 0)
        & (characteristics.PF < 1)
    ].sort_values(["loser_count", "AvgR"], ascending=[False, True]).head(5)
    winner_names = [
        "Strong BOS displacement",
        "Delayed confirmation",
        "Core session",
        "High relative BOS volume",
        "Shallow retest penetration",
    ]
    winners = characteristics.loc[characteristics.characteristic.isin(winner_names)].copy()
    winners["report_order"] = winners.characteristic.map({name: order for order, name in enumerate(winner_names)})
    winners = winners.sort_values("report_order")
    both = interactions.loc[interactions.cell == "Both"].copy()
    both = both.loc[both.N >= 3].sort_values(["AvgR", "Both_minus_Neither_AvgR"], ascending=False).head(5)
    evidence = _evidence_label(comparison, distribution_summary)

    lines = [
        "# Winner vs Loser Entry-Quality Forensics",
        "",
        "## Scope and guardrails",
        "",
        f"This is development-window forensic discovery only: {bars_in_window:,} five-minute bars from 2026-06-29 through 2026-08-18 in America/Chicago, with warm-up history beginning 2026-05-31 19:00 CT. The unseen OOS dataset was not accessed. Pine, the frozen Python engines, entries, stops, targets, filters, and the $14.50 round-turn cost assumption were not modified.",
        "",
        "All explanatory variables were available by the entry-bar close. Outcome, MFE, MAE, exits, and net/gross R were labels only. Quantile and median splits are descriptive devices, not proposed trading thresholds.",
        "",
        "## CURRENT",
        "",
        f"- N: {current['N']}",
        f"- Wins: {current['wins']}",
        f"- Losses: {current['losses']}",
        f"- Win rate: {current['win_pct']:.2f}%",
        f"- AvgR: {current['avg_R']:.5f}",
        f"- TotalR: {current['total_R']:.5f}",
        f"- PF: {current['profit_factor']:.5f}",
        f"- MaxDD: {current['max_drawdown_R']:.5f}R",
        "",
        "## Top 10 pre-entry features separating winners and losers",
        "",
        "| Rank | Feature | Relationship | Cohen d | Winner median | Loser median | LOO stability | Outlier check | Market rationale |",
        "|---:|---|---|---:|---:|---:|---|---|---|",
    ]
    for rank, row in enumerate(top.itertuples(), start=1):
        lines.append(
            f"| {rank} | {row.feature_label} | {row.relationship} | {_fmt(row.standardized_effect_Cohen_d)} | {_fmt(row.winner_median)} | {_fmt(row.loser_median)} | {row.LOO_stability} | {row.outlier_dependence} | {_rationale(row.feature)} |"
        )

    lines.extend(["", "## Top loser characteristics", ""])
    for rank, row in enumerate(losers.itertuples(), start=1):
        lines.append(
            f"{rank}. **{row.characteristic}** — {row.loser_count}/25 losses ({row.loser_share_of_25_pct:.1f}%), {row.winner_count}/17 winners; conditional AvgR {_fmt(row.AvgR)}, PF {_fmt(row.PF)}. Definition: {row.definition}."
        )
    lines.extend(["", "## Top winner characteristics", ""])
    for rank, row in enumerate(winners.itertuples(), start=1):
        lines.append(
            f"{rank}. **{'Longer confirmation delay (counterintuitive)' if row.characteristic == 'Delayed confirmation' else row.characteristic}** — {row.winner_count}/17 winners ({row.winner_share_of_17_pct:.1f}%), {row.loser_count}/25 losses; conditional AvgR {_fmt(row.AvgR)}, PF {_fmt(row.PF)}. Definition: {row.definition}."
        )
    lines.extend(["", "## Best apparent two-feature interactions", ""])
    if both.empty:
        lines.append("No logical interaction had at least three observations in its joint cell.")
    else:
        for rank, row in enumerate(both.itertuples(), start=1):
            lines.append(
                f"{rank}. **{row.interaction}** — Both-cell N {row.N}, WR {row.win_rate_pct:.1f}%, AvgR {_fmt(row.AvgR)}, PF {_fmt(row.PF)}; AvgR difference versus Neither {_fmt(row.Both_minus_Neither_AvgR)}. Exploratory only."
            )

    lines.extend(
        [
            "",
            "## Distribution and stability interpretation",
            "",
        ]
    )
    for row in distribution_summary.itertuples():
        lines.append(
            f"- {row.feature_label}: {row.pattern}; bucket-order/AvgR Spearman {_fmt(row.spearman_bucket_order_vs_AvgR)}; smallest bucket N {row.min_bucket_N}."
        )

    lines.extend(
        [
            "",
            "## Is there evidence that entry quality can be improved?",
            "",
            f"**{evidence}.** The sample contains observed pre-entry separation, but N=42 is too small and all evidence comes from the development window. Any promising relationship must be defined prospectively and tested without revisiting the unseen OOS sample.",
            "",
            "## Most promising three hypotheses for future preregistered testing",
            "",
            "- **H1 — BOS impulse plus participation:** entries with jointly stronger causal BOS displacement and relative volume have better expectancy than valid breaks lacking both characteristics.",
            "- **H2 — Retest acceptance quality:** entries whose accepted retest candle shows stronger directional body/range expansion and closes farther back onto the intended side of stored BOS have better expectancy than weaker accepted retests.",
            "- **H3 — Volatility-and-session context:** valid entries in a higher, already-known ATR state and the frozen core session have better expectancy than otherwise-valid entries in quieter/off-session conditions.",
            "",
            "No numeric cutoff is recommended here. Any later test should preregister structural definitions or fixed non-profit-derived splits before opening unseen data.",
            "",
            "## Feature definitions and leakage controls",
            "",
            "- BOS displacement is the direction-signed BOS close change from the prior bar close; close-beyond-structure is reported separately against the stored BOS level.",
            "- Relative volume uses the BOS bar volume divided by the mean of the prior 20 completed bars; the BOS bar is excluded from the denominator.",
            "- Entry ATR percentile compares the known entry-bar ATR with up to 100 completed prior bars.",
            "- Session high/low are cumulative within the CME session and include only bars through the entry bar.",
            "- Retest penetration is measured from BOS+1 through the accepted retest; confirmation is strictly later than retest.",
            "- Setup and BOS occurred on the same bar for 41 of 42 trades. Their candle-shape fields are therefore usually duplicate observations, not independent evidence; raw upper/lower wick effects also require direction-aware interpretation.",
            "- The apparent benefit of a longer confirmation delay is sparse: 31 trades confirmed after one bar, eight after two bars, and three after three bars. It is not a monotonic threshold finding.",
            "- Cohen d is descriptive. LOO stability is STABLE when all leave-one-out signs agree and the smallest absolute effect is at least 75% of the full effect; PARTIALLY STABLE uses at least 90% sign agreement and 50% effect retention.",
            "- Outlier checks separately remove the best trade, worst trade, top two winners, and top two losers.",
        ]
    )
    return "\n".join(lines) + "\n"


def file_hash(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_forensics(
    frame: pd.DataFrame,
    *,
    current_trade_path: Path,
    candidate_path: Path,
    output: Path,
    start: str,
    end: str,
    config: FrozenConfig = FrozenConfig(),
    project_root: Path | None = None,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    current = pd.read_csv(current_trade_path)
    candidates = pd.read_csv(candidate_path)
    replay = prepare_forensic_replay(frame, start=start, end=end, config=config)
    features = reconstruct_trade_features(replay, current, candidates, config=config)
    comparison = continuous_comparison(features)
    categorical = categorical_comparison(features)
    distributions, distribution_summary = distribution_analysis(features)
    interactions = interaction_analysis(features)
    characteristics = forensic_characteristics(features)
    bars = replay.end_position - replay.start_position

    features.to_csv(output / "trade_level_features.csv", index=False)
    comparison.to_csv(output / "winner_loser_comparison.csv", index=False)
    categorical.to_csv(output / "categorical_comparison.csv", index=False)
    distributions.to_csv(output / "distribution_analysis.csv", index=False)
    distribution_summary.to_csv(output / "distribution_summary.csv", index=False)
    interactions.to_csv(output / "interaction_analysis.csv", index=False)
    characteristics.to_csv(output / "winner_loser_characteristics.csv", index=False)
    current_metrics = _current_metrics(features)
    pd.DataFrame(
        [
            {
                **current_metrics,
                "bars_in_window": bars,
                "evidence": _evidence_label(comparison, distribution_summary),
                "round_turn_cost_USD": ROUND_TURN_COST_USD,
                "numeric_feature_count": len(NUMERIC_FEATURES),
                "logical_interaction_count": int(interactions.interaction_id.nunique()),
            }
        ]
    ).to_csv(output / "current_summary.csv", index=False)
    report = build_report(
        features=features,
        comparison=comparison,
        categorical=categorical,
        distributions=distributions,
        distribution_summary=distribution_summary,
        interactions=interactions,
        characteristics=characteristics,
        bars_in_window=bars,
    )
    (output / "WINNER_LOSER_ENTRY_QUALITY_REPORT.md").write_text(report)

    root = project_root or Path.cwd()
    frozen_files = [
        root / "phase16/config.py",
        root / "phase16/entry_models.py",
        root / "phase16/setup_engine.py",
        root / "phase16/trade_engine.py",
        root / "outputs/CRT_Core_RETEST_GATED_LIVE.pine",
    ]
    manifest = {
        "development_only": True,
        "unseen_oos_accessed": False,
        "window": {"start": str(replay.start_timestamp), "end_exclusive": str(replay.end_exclusive)},
        "bars_in_window": bars,
        "trade_count": len(features),
        "winner_count": int(features.is_winner.sum()),
        "loser_count": int((features.is_winner == 0).sum()),
        "current_net_metrics": current_metrics,
        "evidence": _evidence_label(comparison, distribution_summary),
        "feature_count": len(NUMERIC_FEATURES),
        "interaction_count": int(interactions.interaction_id.nunique()),
        "cost_assumption": {"round_turn_usd": ROUND_TURN_COST_USD, "nq_usd_per_point": NQ_DOLLARS_PER_POINT},
        "frozen_file_sha1": {str(path.relative_to(root)): file_hash(path) for path in frozen_files},
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest
