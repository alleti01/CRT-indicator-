"""Development-only trade-archetype decomposition for the frozen CRT model.

This module is an analysis consumer.  It does not change the frozen setup,
funnel, trade, risk, stop, target, cost, or Pine implementations.  Archetypes
use information available no later than the confirmation/entry-bar close.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import numpy as np
import pandas as pd

from .backtest import BacktestResult, run_backtest, validation_window
from .config import FrozenConfig
from .focused_hypothesis_testing import _student_t_cdf
from .indicators import (
    add_base_indicators,
    add_previous_closed_htf_regime,
    crt_reference_and_sweeps,
    htf_regime_name,
    score_band,
    session_bucket,
    session_bucket_name,
)
from .liquidity import LiquidityEngine, LiquidityLevel
from .setup_engine import SetupEngine
from .structure import StructureEngine


ROUND_TURN_COST_USD = 14.50
NQ_DOLLARS_PER_POINT = 20.0


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if _finite(denominator) and float(denominator) > 0 else float("nan")


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
    return "With trade" if difference * intended_direction > 0 else "Against trade"


def _level_payload(levels: Sequence[LiquidityLevel], side: str) -> Dict[str, Any]:
    if not levels:
        return {
            "sweep_direction": "None",
            "swept_level_type": "None",
            "swept_level_prices": "[]",
            "swept_level_count": 0,
        }
    level_types = sorted(
        {
            ("Equal high / buy-side" if level.is_equal else "Swing high / buy-side")
            if side == "BSL"
            else ("Equal low / sell-side" if level.is_equal else "Swing low / sell-side")
            for level in levels
        }
    )
    return {
        "sweep_direction": side,
        "swept_level_type": " | ".join(level_types),
        "swept_level_prices": json.dumps([float(level.price) for level in levels], separators=(",", ":")),
        "swept_level_count": len(levels),
    }


@dataclass
class ArchetypeReplay:
    data: pd.DataFrame
    structures: list[Any]
    setups: list[Any]
    liquidity_events: list[Any]
    setup_context: Dict[tuple[int, int], Dict[str, Any]]
    start_timestamp: pd.Timestamp
    end_exclusive: pd.Timestamp


def prepare_archetype_replay(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    config: FrozenConfig,
) -> ArchetypeReplay:
    """Replay frozen engines and capture causal analysis-only setup context."""
    data = frame.tz_convert(config.exchange_timezone).sort_index().copy()
    data = add_base_indicators(data, config)
    data = add_previous_closed_htf_regime(data, config)
    data = data.join(crt_reference_and_sweeps(data))
    data["prior20_volume_mean"] = data.volume.shift(1).rolling(20, min_periods=20).mean()
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)

    structure_engine = StructureEngine(config)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    structures: list[Any] = []
    liquidity_events: list[Any] = []
    setups: list[Any] = []
    setup_context: Dict[tuple[int, int], Dict[str, Any]] = {}
    last_sweep: Dict[int, Dict[str, Any] | None] = {1: None, -1: None}

    for bar_index, row in enumerate(data.itertuples()):
        structure = structure_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.structure_pivot_high),
            pivot_low=float(row.structure_pivot_low),
        )

        bsl_levels = [
            level
            for level in liquidity_engine.buy_side
            if bar_index > level.confirmation_bar and float(row.high) > level.price and float(row.close) < level.price
        ]
        ssl_levels = [
            level
            for level in liquidity_engine.sell_side
            if bar_index > level.confirmation_bar and float(row.low) < level.price and float(row.close) > level.price
        ]
        liquidity = liquidity_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.liquidity_pivot_high),
            pivot_low=float(row.liquidity_pivot_low),
        )
        if bool(bsl_levels) != bool(liquidity.bsl_sweep) or bool(ssl_levels) != bool(liquidity.ssl_sweep):
            raise AssertionError(f"liquidity sweep attribution mismatch at {row.Index}")
        if bsl_levels:
            last_sweep[-1] = {"bar_index": bar_index, **_level_payload(bsl_levels, "BSL")}
        if ssl_levels:
            last_sweep[1] = {"bar_index": bar_index, **_level_payload(ssl_levels, "SSL")}

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
        liquidity_events.append(liquidity)
        setups.append(setup)

        if setup.canonical:
            direction = setup.canonical_direction
            matching_bos = bool(structure.bull_bos if direction == 1 else structure.bear_bos)
            matching_sweep = bool(liquidity.ssl_sweep if direction == 1 else liquidity.bsl_sweep)
            trigger_type = (
                "Matching BOS + liquidity sweep"
                if matching_bos and matching_sweep
                else "Matching BOS only"
                if matching_bos
                else "Matching liquidity sweep only"
                if matching_sweep
                else "Other"
            )
            sweep = last_sweep[direction]
            recent_sweep = (
                sweep
                if sweep is not None and bar_index - int(sweep["bar_index"]) <= config.se_liquidity_lookback
                else None
            )
            if direction == 1:
                structure_type = "Bull CHoCH" if structure.bull_choch else "Bull BOS" if structure.bull_bos else "Recent bull structure"
            else:
                structure_type = "Bear CHoCH" if structure.bear_choch else "Bear BOS" if structure.bear_bos else "Recent bear structure"
            crt_bar_sweep = (
                "Sweep below CRT reference"
                if bool(row.sweep_below) and not bool(row.sweep_above)
                else "Sweep above CRT reference"
                if bool(row.sweep_above) and not bool(row.sweep_below)
                else "Both CRT sweeps"
                if bool(row.sweep_above) and bool(row.sweep_below)
                else "None"
            )
            setup_context[(direction, int(row.Index.value))] = {
                "setup_type": trigger_type,
                "setup_structure_event_type": structure_type,
                "matching_bos_on_setup_bar": matching_bos,
                "matching_liquidity_sweep_on_setup_bar": matching_sweep,
                "liquidity_context": f"Recent {recent_sweep['sweep_direction']}" if recent_sweep else "No recent matching sweep",
                "sweep_age_bars": bar_index - int(recent_sweep["bar_index"]) if recent_sweep else np.nan,
                "sweep_direction": recent_sweep["sweep_direction"] if recent_sweep else "None",
                "swept_level_type": recent_sweep["swept_level_type"] if recent_sweep else "None",
                "swept_level_prices": recent_sweep["swept_level_prices"] if recent_sweep else "[]",
                "swept_level_count": recent_sweep["swept_level_count"] if recent_sweep else 0,
                "crt_bar_sweep_type": crt_bar_sweep,
            }

    return ArchetypeReplay(
        data=data,
        structures=structures,
        setups=setups,
        liquidity_events=liquidity_events,
        setup_context=setup_context,
        start_timestamp=start_ts,
        end_exclusive=end_exclusive,
    )


def verify_archived_baseline(
    current: pd.DataFrame,
    archived: pd.DataFrame,
    *,
    tolerance: float = 1e-9,
) -> pd.DataFrame:
    """Return a field reconciliation and raise unless all 705 trades match."""
    current = current.loc[current.model == "Confirm"].reset_index(drop=True).copy()
    archived = archived.loc[archived.model == "Confirm"].reset_index(drop=True).copy()
    rows: List[Dict[str, Any]] = []
    if len(current) != 705 or len(archived) != 705:
        raise RuntimeError(f"705-TRADE BASELINE MISMATCH: current={len(current)}, archived={len(archived)}")
    if list(current.columns) != list(archived.columns):
        raise RuntimeError("705-TRADE BASELINE MISMATCH: columns differ")
    for column in current.columns:
        if "timestamp" in column:
            left = pd.to_datetime(current[column], utc=True, errors="coerce")
            right = pd.to_datetime(archived[column], utc=True, errors="coerce")
            mismatch = ~((left == right) | (left.isna() & right.isna()))
        elif column in {
            "entry_price", "stop_price", "target_price", "exit_price", "result_R",
            "score", "htf_regime", "session_bucket",
        }:
            left = pd.to_numeric(current[column], errors="coerce")
            right = pd.to_numeric(archived[column], errors="coerce")
            mismatch = ~pd.Series(np.isclose(left, right, rtol=0, atol=tolerance, equal_nan=True))
        else:
            mismatch = current[column].fillna("").astype(str) != archived[column].fillna("").astype(str)
        rows.append({"field": column, "mismatches": int(np.asarray(mismatch).sum())})
    result = pd.DataFrame(rows)
    if int(result.mismatches.sum()) != 0:
        raise RuntimeError(f"705-TRADE BASELINE MISMATCH: {int(result.mismatches.sum())} field mismatches")
    return result


def _volatility_state(percentile: float) -> str:
    if percentile <= 0.33:
        return "LOW"
    if percentile >= 0.67:
        return "HIGH"
    return "MID"


def _retest_behavior(
    *,
    direction: int,
    probe: float,
    close: float,
    bos_level: float,
) -> str:
    signed_penetration = direction * (bos_level - probe)
    if signed_penetration < 0:
        return "Tolerance-only shallow touch"
    if signed_penetration == 0:
        return "Exact BOS touch"
    reclaimed = direction * (close - bos_level) > 0
    return "Penetration + same-bar reclaim" if reclaimed else "Penetration without same-bar reclaim"


def build_trade_archetype_features(
    replay: ArchetypeReplay,
    confirm_trades: pd.DataFrame,
    *,
    config: FrozenConfig,
) -> pd.DataFrame:
    """Create one causal feature row per verified Confirm trade."""
    trades = confirm_trades.copy()
    for column in [
        "setup_timestamp", "bos_timestamp", "retest_timestamp", "confirm_timestamp",
        "entry_timestamp", "exit_timestamp",
    ]:
        trades[column] = _timestamp_series(trades[column], config.exchange_timezone)
    trades = trades.sort_values("entry_timestamp", kind="stable").reset_index(drop=True)
    position_by_time = {int(timestamp.value): position for position, timestamp in enumerate(replay.data.index)}
    chronological_split = len(trades) // 2
    rows: List[Dict[str, Any]] = []

    for trade_number, trade in enumerate(trades.itertuples(), start=1):
        direction = _direction_int(trade.direction)
        positions = {
            name: position_by_time[int(pd.Timestamp(getattr(trade, f"{name}_timestamp")).value)]
            for name in ("setup", "bos", "retest", "confirm", "entry")
        }
        if not (positions["setup"] <= positions["bos"] < positions["retest"] < positions["confirm"] == positions["entry"]):
            raise AssertionError(f"non-causal event sequence at {trade.entry_timestamp}")
        setup_row = replay.data.iloc[positions["setup"]]
        bos_row = replay.data.iloc[positions["bos"]]
        retest_row = replay.data.iloc[positions["retest"]]
        confirm_row = replay.data.iloc[positions["confirm"]]
        setup_structure = replay.structures[positions["setup"]]
        bos_structure = replay.structures[positions["bos"]]
        context = replay.setup_context.get((direction, int(pd.Timestamp(trade.setup_timestamp).value)))
        if context is None:
            raise AssertionError(f"missing canonical setup context at {trade.setup_timestamp}")

        prior_level = bos_structure.previous_active_high if direction == 1 else bos_structure.previous_active_low
        current_level = bos_structure.active_high if direction == 1 else bos_structure.active_low
        bos_level = float(prior_level if _finite(prior_level) else current_level)
        if not _finite(bos_level):
            raise AssertionError(f"missing BOS level at {trade.bos_timestamp}")

        setup_parts = _candle_parts(setup_row)
        bos_parts = _candle_parts(bos_row)
        retest_parts = _candle_parts(retest_row)
        confirm_parts = _candle_parts(confirm_row)
        setup_atr, bos_atr, retest_atr, confirm_atr = map(
            float, (setup_row.atr, bos_row.atr, retest_row.atr, confirm_row.atr)
        )
        prior_close = float(replay.data.iloc[positions["bos"] - 1].close) if positions["bos"] > 0 else float(bos_row.open)
        bos_displacement = direction * (float(bos_row.close) - prior_close)
        close_beyond_bos = direction * (float(bos_row.close) - bos_level)
        retest_probe = float(retest_row.low) if direction == 1 else float(retest_row.high)
        retest_penetration = max(0.0, direction * (bos_level - retest_probe))
        retest_reclaim = direction * (float(retest_row.close) - bos_level)
        retest_toward_wick = retest_parts["lower"] if direction == 1 else retest_parts["upper"]
        retest_away_wick = retest_parts["upper"] if direction == 1 else retest_parts["lower"]
        confirm_rejection_wick = confirm_parts["lower"] if direction == 1 else confirm_parts["upper"]

        trailing_atr = replay.data.atr.iloc[max(0, positions["entry"] - 100):positions["entry"]].dropna()
        atr_percentile = float((trailing_atr <= confirm_atr).mean()) if len(trailing_atr) else float("nan")
        risk_points = abs(float(trade.entry_price) - float(trade.stop_price))
        cost_r = ROUND_TURN_COST_USD / (risk_points * NQ_DOLLARS_PER_POINT)
        gross_r = float(trade.result_R)
        net_r = gross_r - cost_r

        path = replay.data.loc[(replay.data.index > trade.entry_timestamp) & (replay.data.index <= trade.exit_timestamp)]
        if path.empty or risk_points <= 0:
            mfe_r = mae_r = 0.0
        elif direction == 1:
            mfe_r = max(0.0, float((path.high.max() - trade.entry_price) / risk_points))
            mae_r = max(0.0, float((trade.entry_price - path.low.min()) / risk_points))
        else:
            mfe_r = max(0.0, float((trade.entry_price - path.low.min()) / risk_points))
            mae_r = max(0.0, float((path.high.max() - trade.entry_price) / risk_points))

        setup_prior = setup_structure.previous_active_high if direction == 1 else setup_structure.previous_active_low
        setup_current = setup_structure.active_high if direction == 1 else setup_structure.active_low
        setup_level = float(setup_prior if _finite(setup_prior) else setup_current)
        setup_bos_same = positions["setup"] == positions["bos"]
        behavior = _retest_behavior(
            direction=direction,
            probe=retest_probe,
            close=float(retest_row.close),
            bos_level=bos_level,
        )
        session_name = session_bucket_name(int(trade.session_bucket))
        setup_session_name = session_bucket_name(session_bucket(pd.Timestamp(trade.setup_timestamp)))
        htf_name = htf_regime_name(int(trade.htf_regime))
        setup_htf_name = htf_regime_name(int(setup_row.htf_regime))
        bos_retest_bars = positions["retest"] - positions["bos"]
        retest_confirm_bars = positions["confirm"] - positions["retest"]

        rows.append(
            {
                "trade_id": f"A{trade_number:04d}",
                "date": trade.entry_timestamp.date().isoformat(),
                "year": int(trade.entry_timestamp.year),
                "quarter": f"{trade.entry_timestamp.year}-Q{(trade.entry_timestamp.month - 1) // 3 + 1}",
                "chronological_half": "First 50%" if trade_number <= chronological_split else "Second 50%",
                "direction": str(trade.direction),
                "crt_direction": str(trade.direction),
                "session": session_name,
                "setup_session": setup_session_name,
                "HTF_regime": htf_name,
                "setup_HTF_regime": setup_htf_name,
                "volatility_state": _volatility_state(atr_percentile),
                "setup_timestamp": trade.setup_timestamp,
                "setup_score": float(trade.score),
                "setup_score_band": score_band(float(trade.score)),
                "setup_type": context["setup_type"],
                "setup_structure_event_type": context["setup_structure_event_type"],
                "matching_bos_on_setup_bar": context["matching_bos_on_setup_bar"],
                "matching_liquidity_sweep_on_setup_bar": context["matching_liquidity_sweep_on_setup_bar"],
                "liquidity_context": context["liquidity_context"],
                "sweep_direction": context["sweep_direction"],
                "swept_level_type": context["swept_level_type"],
                "swept_level_prices": context["swept_level_prices"],
                "swept_level_count": context["swept_level_count"],
                "sweep_age_bars": context["sweep_age_bars"],
                "crt_bar_sweep_type": context["crt_bar_sweep_type"],
                "setup_structure_level": setup_level,
                "setup_close_beyond_structure_atr": _ratio(direction * (float(setup_row.close) - setup_level), setup_atr),
                "setup_body_atr": _ratio(setup_parts["body"], setup_atr),
                "setup_range_atr": _ratio(setup_parts["range"], setup_atr),
                "setup_candle_direction": _candle_direction(setup_row, direction),
                "bos_timestamp": trade.bos_timestamp,
                "bos_direction": str(trade.direction),
                "bos_level": bos_level,
                "setup_to_bos_bars": positions["bos"] - positions["setup"],
                "same_bar_setup_bos": setup_bos_same,
                "setup_bos_timing": "Same-bar Setup+BOS" if setup_bos_same else "Delayed BOS",
                "bos_displacement_atr": _ratio(bos_displacement, bos_atr),
                "bos_close_beyond_structure_atr": _ratio(close_beyond_bos, bos_atr),
                "bos_body_atr": _ratio(bos_parts["body"], bos_atr),
                "bos_range_atr": _ratio(bos_parts["range"], bos_atr),
                "bos_body_pct_range": bos_parts["body_pct"],
                "bos_upper_wick_ratio": bos_parts["upper_ratio"],
                "bos_lower_wick_ratio": bos_parts["lower_ratio"],
                "bos_candle_direction": _candle_direction(bos_row, direction),
                "bos_relative_volume_20": _ratio(float(bos_row.volume), float(bos_row.prior20_volume_mean)),
                "retest_timestamp": trade.retest_timestamp,
                "bars_BOS_to_retest": bos_retest_bars,
                "bos_retest_timing": "Immediate retest (1 bar)" if bos_retest_bars == 1 else "Delayed retest (2+ bars)",
                "retest_probe_price": retest_probe,
                "retest_penetration_points": retest_penetration,
                "retest_penetration_atr": _ratio(retest_penetration, retest_atr),
                "retest_reclaim_distance_atr": _ratio(retest_reclaim, retest_atr),
                "retest_range_atr": _ratio(retest_parts["range"], retest_atr),
                "retest_body_atr": _ratio(retest_parts["body"], retest_atr),
                "retest_upper_wick_ratio": retest_parts["upper_ratio"],
                "retest_lower_wick_ratio": retest_parts["lower_ratio"],
                "retest_wick_toward_atr": _ratio(retest_toward_wick, retest_atr),
                "retest_wick_away_atr": _ratio(retest_away_wick, retest_atr),
                "retest_candle_direction": _candle_direction(retest_row, direction),
                "retest_behavior": behavior,
                "retest_merely_touched_bos": behavior in {"Tolerance-only shallow touch", "Exact BOS touch"},
                "retest_meaningfully_penetrated": retest_penetration > 0,
                "retest_reclaimed_at_close": retest_reclaim > 0,
                "confirmation_timestamp": trade.confirm_timestamp,
                "bars_retest_to_confirmation": retest_confirm_bars,
                "retest_confirm_timing": "Immediate confirmation (1 bar)" if retest_confirm_bars == 1 else "Delayed confirmation (2+ bars)",
                "confirmation_body_atr": _ratio(confirm_parts["body"], confirm_atr),
                "confirmation_range_atr": _ratio(confirm_parts["range"], confirm_atr),
                "confirmation_body_pct_range": confirm_parts["body_pct"],
                "confirmation_close_displacement_from_BOS_atr": _ratio(direction * (float(confirm_row.close) - bos_level), confirm_atr),
                "confirmation_displacement_from_retest_close_atr": _ratio(direction * (float(confirm_row.close) - float(retest_row.close)), confirm_atr),
                "confirmation_rejection_wick_atr": _ratio(confirm_rejection_wick, confirm_atr),
                "confirmation_direction": _candle_direction(confirm_row, direction),
                "entry_timestamp": trade.entry_timestamp,
                "entry_price": float(trade.entry_price),
                "entry_ATR": confirm_atr,
                "entry_ATR_percentile_prior_100": atr_percentile,
                "stop_price": float(trade.stop_price),
                "stop_distance_points": risk_points,
                "stop_distance_ATR": _ratio(risk_points, confirm_atr),
                "target_price": float(trade.target_price),
                "target_distance_points": abs(float(trade.target_price) - float(trade.entry_price)),
                "target_structure": f"Fixed {config.trade_target_r:.2f}R target",
                "cost_R": cost_r,
                "gross_R": gross_r,
                "net_R": net_r,
                "outcome": "Win" if net_r > 0 else "Loss" if net_r < 0 else "Flat",
                "MFE_R": mfe_r,
                "MAE_R": mae_r,
                "exit_timestamp": trade.exit_timestamp,
                "exit_price": float(trade.exit_price),
                "exit_reason": str(trade.exit_reason),
            }
        )

    result = pd.DataFrame(rows)
    if len(result) != 705:
        raise AssertionError(f"archetype feature reconstruction produced {len(result)} trades, expected 705")
    return result


def _drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    equity = values.astype(float).cumsum().to_numpy()
    peaks = np.maximum.accumulate(np.r_[0.0, equity])[:-1]
    return float(np.max(np.maximum(0.0, peaks - equity), initial=0.0))


def _basis_metrics(frame: pd.DataFrame, column: str, prefix: str) -> Dict[str, Any]:
    values = frame.sort_values("exit_timestamp", kind="stable")[column].astype(float) if len(frame) else pd.Series(dtype=float)
    profit = float(values[values > 0].sum())
    loss = float(-values[values < 0].sum())
    pf = profit / loss if loss > 0 else (99.9 if profit > 0 else 0.0)
    return {
        f"{prefix}_wins": int((values > 0).sum()),
        f"{prefix}_losses": int((values < 0).sum()),
        f"{prefix}_flats": int((values == 0).sum()),
        f"{prefix}_win_rate_pct": float((values > 0).mean() * 100.0) if len(values) else 0.0,
        f"{prefix}_AvgR": float(values.mean()) if len(values) else 0.0,
        f"{prefix}_median_R": float(values.median()) if len(values) else 0.0,
        f"{prefix}_TotalR": float(values.sum()) if len(values) else 0.0,
        f"{prefix}_PF": float(pf),
        f"{prefix}_MaxDD_R": _drawdown(values),
    }


def performance(frame: pd.DataFrame, total_trades: int = 705) -> Dict[str, Any]:
    return {
        "N": int(len(frame)),
        "pct_all_trades": float(len(frame) * 100.0 / total_trades) if total_trades else 0.0,
        **_basis_metrics(frame, "gross_R", "gross"),
        **_basis_metrics(frame, "net_R", "net"),
        "avg_MFE_R": float(frame.MFE_R.mean()) if len(frame) else 0.0,
        "avg_MAE_R": float(frame.MAE_R.mean()) if len(frame) else 0.0,
    }


def sample_label(count: int) -> str:
    return "SMALL SAMPLE" if count < 30 else "ADEQUATE N"


SINGLE_FACTORS: Mapping[str, str] = {
    "Direction": "direction",
    "Entry session": "session",
    "Entry HTF regime": "HTF_regime",
    "Setup HTF regime": "setup_HTF_regime",
    "Setup trigger type": "setup_type",
    "Liquidity context": "liquidity_context",
    "CRT bar sweep": "crt_bar_sweep_type",
    "Setup/BOS timing": "setup_bos_timing",
    "BOS→Retest timing": "bos_retest_timing",
    "Retest→Confirm timing": "retest_confirm_timing",
    "Retest behavior": "retest_behavior",
    "Volatility state": "volatility_state",
}


def build_archetype_summary(features: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, pd.DataFrame]]:
    rows: List[Dict[str, Any]] = []
    selections: Dict[str, pd.DataFrame] = {}
    for dimension, column in SINGLE_FACTORS.items():
        for category, group in features.groupby(column, dropna=False, sort=True):
            key = f"SF::{dimension}::{category}"
            rows.append(
                {
                    "analysis_level": "Single factor",
                    "dimension": dimension,
                    "category": str(category),
                    "family_id": "",
                    "family_definition": "",
                    "direction_slice": "All",
                    "sample_label": sample_label(len(group)),
                    **performance(group, len(features)),
                }
            )
            selections[key] = group
            if group.direction.nunique() > 1:
                for direction, directional in group.groupby("direction", sort=True):
                    if len(directional) < 30:
                        continue
                    rows.append(
                        {
                            "analysis_level": "Single factor direction slice",
                            "dimension": dimension,
                            "category": str(category),
                            "family_id": "",
                            "family_definition": "",
                            "direction_slice": str(direction),
                            "sample_label": sample_label(len(directional)),
                            **performance(directional, len(features)),
                        }
                    )

    family_selections: Dict[str, pd.DataFrame] = {}
    family_columns = ["direction", "setup_bos_timing", "retest_behavior"]
    for values, group in features.groupby(family_columns, dropna=False, sort=True):
        direction, timing, behavior = map(str, values)
        family_id = f"F::{direction}::{timing}::{behavior}"
        definition = f"{direction} × {timing} × {behavior}"
        rows.append(
            {
                "analysis_level": "Three-dimension structural family",
                "dimension": "Direction × Setup/BOS timing × Retest behavior",
                "category": definition,
                "family_id": family_id,
                "family_definition": definition,
                "direction_slice": direction,
                "sample_label": sample_label(len(group)),
                **performance(group, len(features)),
            }
        )
        family_selections[family_id] = group
    result = pd.DataFrame(rows)
    return result, family_selections


def welch_two_sided(selected: pd.Series, complement: pd.Series) -> tuple[float, float, float]:
    a = selected.astype(float).dropna().to_numpy()
    b = complement.astype(float).dropna().to_numpy()
    if len(a) < 2 or len(b) < 2:
        return np.nan, np.nan, np.nan
    va, vb = float(np.var(a, ddof=1)), float(np.var(b, ddof=1))
    standard_error_sq = va / len(a) + vb / len(b)
    if standard_error_sq <= 0:
        return np.nan, np.nan, np.nan
    statistic = (float(np.mean(a)) - float(np.mean(b))) / math.sqrt(standard_error_sq)
    denominator = (va / len(a)) ** 2 / (len(a) - 1) + (vb / len(b)) ** 2 / (len(b) - 1)
    degrees = standard_error_sq**2 / denominator if denominator > 0 else np.nan
    p_value = 2.0 * (1.0 - _student_t_cdf(abs(statistic), degrees)) if _finite(degrees) else np.nan
    return float(statistic), float(degrees), float(min(1.0, p_value))


def _bh_adjust(values: pd.Series) -> pd.Series:
    result = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna().sort_values()
    if valid.empty:
        return result
    raw = valid.to_numpy() * len(valid) / np.arange(1, len(valid) + 1)
    adjusted = np.minimum.accumulate(raw[::-1])[::-1]
    result.loc[valid.index] = np.minimum(1.0, adjusted)
    return result


def _outlier_metrics(group: pd.DataFrame) -> Dict[str, Any]:
    winners = group.loc[group.net_R > 0].sort_values("net_R", ascending=False)
    top_one_count = max(1, math.ceil(len(group) * 0.01))
    removals = {
        "remove_best_trade": list(group.nlargest(1, "net_R").trade_id),
        "remove_top_1pct_winners": list(winners.head(top_one_count).trade_id),
        "remove_top_3_winners": list(winners.head(3).trade_id),
    }
    payload: Dict[str, Any] = {}
    survives = True
    for name, ids in removals.items():
        metrics = performance(group.loc[~group.trade_id.isin(ids)], len(group))
        payload[f"{name}_N"] = metrics["N"]
        payload[f"{name}_net_AvgR"] = metrics["net_AvgR"]
        payload[f"{name}_net_TotalR"] = metrics["net_TotalR"]
        payload[f"{name}_net_PF"] = metrics["net_PF"]
        survives = survives and metrics["net_AvgR"] > 0 and metrics["net_PF"] > 1
    payload["survives_outlier_removal"] = bool(survives)
    return payload


def build_family_robustness(
    features: pd.DataFrame,
    families: Mapping[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: List[Dict[str, Any]] = []
    stability_rows: List[Dict[str, Any]] = []
    total_loss_magnitude = float(-features.loc[features.net_R < 0, "net_R"].sum())
    for family_id, group in families.items():
        if len(group) < 30:
            continue
        complement = features.loc[~features.trade_id.isin(group.trade_id)]
        definition = str(group.iloc[0].direction) + " × " + str(group.iloc[0].setup_bos_timing) + " × " + str(group.iloc[0].retest_behavior)
        family_metrics = performance(group, len(features))
        complement_metrics = performance(complement, len(features))
        yearly_total: Dict[str, float] = {}
        half_total: Dict[str, float] = {}
        for period_type, column in (("Year", "year"), ("Chronological half", "chronological_half")):
            for period, period_group in group.groupby(column, sort=True):
                metrics = performance(period_group, len(features))
                stability_rows.append(
                    {
                        "family_id": family_id,
                        "family_definition": definition,
                        "period_type": period_type,
                        "period": str(period),
                        **metrics,
                    }
                )
                if period_type == "Year":
                    yearly_total[str(period)] = metrics["net_TotalR"]
                else:
                    half_total[str(period)] = metrics["net_TotalR"]
        positive_years = sum(value > 0 for value in yearly_total.values())
        negative_years = sum(value < 0 for value in yearly_total.values())
        positive_halves = sum(value > 0 for value in half_total.values())
        negative_halves = sum(value < 0 for value in half_total.values())
        time_stable_positive = bool(
            len(yearly_total) >= 2
            and positive_years >= math.ceil(len(yearly_total) * 2 / 3)
            and len(half_total) == 2
            and positive_halves == 2
        )
        time_stable_negative = bool(
            len(yearly_total) >= 2
            and negative_years >= math.ceil(len(yearly_total) * 2 / 3)
            and len(half_total) == 2
            and negative_halves == 2
        )
        statistic, degrees, p_value = welch_two_sided(group.net_R, complement.net_R)
        rows.append(
            {
                "family_id": family_id,
                "family_definition": definition,
                **{f"family_{key}": value for key, value in family_metrics.items()},
                **{f"complement_{key}": value for key, value in complement_metrics.items()},
                "net_AvgR_difference_family_minus_complement": family_metrics["net_AvgR"] - complement_metrics["net_AvgR"],
                "positive_years": positive_years,
                "negative_years": negative_years,
                "total_years": len(yearly_total),
                "positive_halves": positive_halves,
                "negative_halves": negative_halves,
                "time_stable_positive": time_stable_positive,
                "time_stable_negative": time_stable_negative,
                "yearly_net_TotalR_json": json.dumps(yearly_total, separators=(",", ":")),
                "half_net_TotalR_json": json.dumps(half_total, separators=(",", ":")),
                "share_of_strategy_loss_magnitude_pct": float(-group.loc[group.net_R < 0, "net_R"].sum() * 100.0 / total_loss_magnitude) if total_loss_magnitude else 0.0,
                "welch_t": statistic,
                "welch_degrees_freedom": degrees,
                "raw_p_two_sided": p_value,
                **_outlier_metrics(group),
            }
        )
    complements = pd.DataFrame(rows)
    if complements.empty:
        return complements, pd.DataFrame(stability_rows)
    complements["BH_FDR_q"] = _bh_adjust(complements.raw_p_two_sided)
    complements["FDR_significant_0_05"] = complements.BH_FDR_q.lt(0.05).fillna(False)
    complements["robust_positive_family"] = (
        (complements.family_net_AvgR > 0)
        & (complements.family_net_PF > 1)
        & complements.time_stable_positive
        & complements.survives_outlier_removal
        & complements.FDR_significant_0_05
    )
    complements["robust_negative_family"] = (
        (complements.family_net_AvgR < 0)
        & (complements.family_net_PF < 1)
        & complements.time_stable_negative
        & complements.FDR_significant_0_05
    )
    complements["tested_family_count"] = len(complements)
    complements["FDR_survivor_count"] = int(complements.FDR_significant_0_05.sum())
    return complements.sort_values("family_net_AvgR", ascending=False, kind="stable").reset_index(drop=True), pd.DataFrame(stability_rows)


def _select_best(complements: pd.DataFrame) -> pd.Series:
    robust = complements.loc[complements.robust_positive_family]
    if not robust.empty:
        return robust.sort_values(["family_net_AvgR", "family_N"], ascending=[False, False], kind="stable").iloc[0]
    profitable = complements.loc[(complements.family_net_AvgR > 0) & (complements.family_net_PF > 1)]
    if not profitable.empty:
        return profitable.sort_values(["family_net_AvgR", "family_N"], ascending=[False, False], kind="stable").iloc[0]
    return complements.sort_values(["family_net_AvgR", "family_N"], ascending=[False, False], kind="stable").iloc[0]


def _select_worst(complements: pd.DataFrame) -> pd.Series:
    robust = complements.loc[complements.robust_negative_family]
    if not robust.empty:
        return robust.sort_values("family_net_TotalR", ascending=True, kind="stable").iloc[0]
    coherent = complements.loc[complements.time_stable_negative & (complements.family_net_AvgR < 0)]
    if not coherent.empty:
        return coherent.sort_values("family_net_TotalR", ascending=True, kind="stable").iloc[0]
    return complements.sort_values("family_net_TotalR", ascending=True, kind="stable").iloc[0]


def build_cumulative_data(features: pd.DataFrame, best_family_id: str) -> pd.DataFrame:
    family = features.loc[features.family_id == best_family_id].sort_values("exit_timestamp", kind="stable")
    complement = features.loc[features.family_id != best_family_id].sort_values("exit_timestamp", kind="stable")
    long = features.loc[features.direction == "Long"].sort_values("exit_timestamp", kind="stable")
    short = features.loc[features.direction == "Short"].sort_values("exit_timestamp", kind="stable")
    maximum = max(map(len, (family, complement, long, short)))

    def values(frame: pd.DataFrame) -> list[Any]:
        cumulative = frame.net_R.cumsum().tolist()
        return cumulative + [None] * (maximum - len(cumulative))

    return pd.DataFrame(
        {
            "trade_sequence": np.arange(1, maximum + 1),
            "best_family_cumulative_net_R": values(family),
            "complement_cumulative_net_R": values(complement),
            "long_cumulative_net_R": values(long),
            "short_cumulative_net_R": values(short),
        }
    )


def _family_id_series(features: pd.DataFrame) -> pd.Series:
    return (
        "F::"
        + features.direction.astype(str)
        + "::"
        + features.setup_bos_timing.astype(str)
        + "::"
        + features.retest_behavior.astype(str)
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fmt(value: Any, digits: int = 4) -> str:
    return "—" if not _finite(value) else f"{float(value):.{digits}f}"


def build_report(
    *,
    baseline: Mapping[str, Any],
    direction_rows: pd.DataFrame,
    timing_rows: pd.DataFrame,
    best: pd.Series,
    worst: pd.Series,
    stability: pd.DataFrame,
    complements: pd.DataFrame,
    classification: str,
) -> str:
    def category_row(frame: pd.DataFrame, category: str) -> pd.Series:
        return frame.loc[(frame.category == category) & (frame.direction_slice == "All")].iloc[0]

    long = category_row(direction_rows, "Long")
    short = category_row(direction_rows, "Short")
    same = category_row(timing_rows, "Same-bar Setup+BOS")
    delayed = category_row(timing_rows, "Delayed BOS")
    best_periods = stability.loc[stability.family_id == best.family_id]
    best_years = best_periods.loc[best_periods.period_type == "Year"]
    first = best_periods.loc[(best_periods.period_type == "Chronological half") & (best_periods.period == "First 50%")].iloc[0]
    second = best_periods.loc[(best_periods.period_type == "Chronological half") & (best_periods.period == "Second 50%")].iloc[0]
    year_text = "; ".join(
        f"{row.period}: N {int(row.N)}, AvgR {_fmt(row.net_AvgR)}, TotalR {_fmt(row.net_TotalR, 2)}, PF {_fmt(row.net_PF)}"
        for row in best_years.itertuples()
    )
    robust_found = bool(complements.robust_positive_family.any() or complements.robust_negative_family.any())
    fdr_survivors = int(complements.FDR_significant_0_05.sum())
    lines = [
        "# Trade Archetype / Setup-Family Decomposition",
        "",
        "## Executive summary",
        "",
        f"The complete 705-trade development baseline reproduced exactly with zero mismatches across every archived trade field. The analysis used only already-exposed 2024-01-01 through 2026-06-26 data, kept the $14.50 round-turn cost, and did not modify Pine or any frozen strategy component. Final classification: **{classification}**.",
        "",
        "## Required final report",
        "",
        "BASELINE REPRODUCED:",
        "YES",
        "",
        "705 TRADES VERIFIED:",
        "YES",
        "",
        "LONG:",
        f"N = {int(long.N)}",
        f"AvgR = {_fmt(long.net_AvgR, 5)}",
        f"TotalR = {_fmt(long.net_TotalR, 5)}",
        f"PF = {_fmt(long.net_PF, 5)}",
        "",
        "SHORT:",
        f"N = {int(short.N)}",
        f"AvgR = {_fmt(short.net_AvgR, 5)}",
        f"TotalR = {_fmt(short.net_TotalR, 5)}",
        f"PF = {_fmt(short.net_PF, 5)}",
        "",
        "SAME-BAR SETUP+BOS:",
        f"N = {int(same.N)}",
        f"AvgR = {_fmt(same.net_AvgR, 5)}",
        f"TotalR = {_fmt(same.net_TotalR, 5)}",
        f"PF = {_fmt(same.net_PF, 5)}",
        "",
        "DELAYED BOS:",
        f"N = {int(delayed.N)}",
        f"AvgR = {_fmt(delayed.net_AvgR, 5)}",
        f"TotalR = {_fmt(delayed.net_TotalR, 5)}",
        f"PF = {_fmt(delayed.net_PF, 5)}",
        "",
        "BEST STRUCTURAL FAMILY:",
        f"Definition = {best.family_definition}",
        f"N = {int(best.family_N)}",
        f"Retention = {_fmt(best.family_pct_all_trades, 2)}%",
        f"AvgR = {_fmt(best.family_net_AvgR, 5)}",
        f"TotalR = {_fmt(best.family_net_TotalR, 5)}",
        f"PF = {_fmt(best.family_net_PF, 5)}",
        f"MaxDD = {_fmt(best.family_net_MaxDD_R, 5)}R",
        "",
        "COMPLEMENT:",
        f"N = {int(best.complement_N)}",
        f"AvgR = {_fmt(best.complement_net_AvgR, 5)}",
        f"TotalR = {_fmt(best.complement_net_TotalR, 5)}",
        f"PF = {_fmt(best.complement_net_PF, 5)}",
        "",
        "YEAR STABILITY:",
        year_text,
        "",
        "FIRST HALF:",
        f"AvgR = {_fmt(first.net_AvgR, 5)}",
        f"PF = {_fmt(first.net_PF, 5)}",
        "",
        "SECOND HALF:",
        f"AvgR = {_fmt(second.net_AvgR, 5)}",
        f"PF = {_fmt(second.net_PF, 5)}",
        "",
        "REMOVE TOP 1% WINNERS:",
        f"AvgR = {_fmt(best.remove_top_1pct_winners_net_AvgR, 5)}",
        f"TotalR = {_fmt(best.remove_top_1pct_winners_net_TotalR, 5)}",
        f"PF = {_fmt(best.remove_top_1pct_winners_net_PF, 5)}",
        "",
        "WORST STRUCTURAL FAMILY:",
        f"Definition = {worst.family_definition}",
        f"N = {int(worst.family_N)}",
        f"AvgR = {_fmt(worst.family_net_AvgR, 5)}",
        f"TotalR = {_fmt(worst.family_net_TotalR, 5)}",
        f"PF = {_fmt(worst.family_net_PF, 5)}",
        f"Share of strategy losses = {_fmt(worst.share_of_strategy_loss_magnitude_pct, 2)}%",
        "",
        "MULTIPLE-TESTING RESULT:",
        f"{len(complements)} adequate-N structural families tested with two-sided Welch comparisons against their complements; {fdr_survivors} survived Benjamini-Hochberg FDR at 5%.",
        "",
        "ROBUST ARCHETYPE FOUND:",
        "YES" if robust_found else "NO",
        "",
        "FINAL CLASSIFICATION:",
        classification,
        "",
        "## Method and interpretation",
        "",
        f"Primary net baseline after costs: N {baseline['N']}, wins {baseline['net_wins']}, losses {baseline['net_losses']}, WR {_fmt(baseline['net_win_rate_pct'], 2)}%, AvgR {_fmt(baseline['net_AvgR'], 5)}, TotalR {_fmt(baseline['net_TotalR'], 2)}, PF {_fmt(baseline['net_PF'], 4)}, MaxDD {_fmt(baseline['net_MaxDD_R'], 2)}R.",
        "",
        "The only three-dimension family definition tested was Direction × same-bar/delayed BOS × objective retest behavior. Retest behavior used the frozen BOS boundary without a fitted threshold: tolerance-only shallow touch, exact BOS touch, penetration with same-bar reclaim, or penetration without same-bar reclaim. Single-factor direction, frozen sessions, HTF regimes, actual setup triggers, liquidity context, CRT-bar sweep, timing, retest behavior, and causal volatility state are descriptive tables—not candidate searches.",
        "",
        "MFE, MAE, exit, and outcome were used only as evaluation labels after the entry. No post-entry field defines any archetype. Families below N=30 remain visible but are labeled SMALL SAMPLE.",
    ]
    if classification == "D — STRATEGY HAS NO ROBUST EDGE":
        lines.extend(["", "The decomposition does not rescue the negative larger-history expectancy. No entry filter or family exclusion should be implemented from this forensic phase."])
    return "\n".join(lines) + "\n"


def run_trade_archetype_decomposition(
    frame: pd.DataFrame,
    *,
    archived_trade_path: Path,
    output: Path,
    start: str = "2024-01-01",
    end: str = "2026-06-26",
    config: FrozenConfig = FrozenConfig(),
    project_root: Path | None = None,
) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    current_result: BacktestResult = run_backtest(frame, start=start, end=end, config=config)
    if current_result.coverage != "FULL DATA":
        raise RuntimeError("705-trade development window is not FULL DATA")
    archived = pd.read_csv(archived_trade_path)
    reconciliation = verify_archived_baseline(current_result.trades, archived)
    confirm = current_result.trades.loc[current_result.trades.model == "Confirm"].copy()

    replay = prepare_archetype_replay(frame, start=start, end=end, config=config)
    features = build_trade_archetype_features(replay, confirm, config=config)
    features["family_id"] = _family_id_series(features)
    summary, family_selections = build_archetype_summary(features)
    complements, stability = build_family_robustness(features, family_selections)
    best = _select_best(complements)
    worst = _select_worst(complements)
    cumulative = build_cumulative_data(features, str(best.family_id))
    baseline = performance(features, len(features))

    robust_found = bool(complements.robust_positive_family.any() or complements.robust_negative_family.any())
    promising = complements.loc[
        (complements.family_net_AvgR > 0)
        & (complements.family_net_PF > 1)
        & complements.time_stable_positive
        & complements.survives_outlier_removal
    ]
    classification = (
        "A — ROBUST ARCHETYPE DIFFERENCE"
        if robust_found
        else "B — PROMISING BUT UNPROVEN"
        if not promising.empty
        else "D — STRATEGY HAS NO ROBUST EDGE"
        if baseline["net_AvgR"] <= 0 or baseline["net_PF"] <= 1
        else "C — NO MEANINGFUL ARCHETYPE DIFFERENCE"
    )

    direction_rows = summary.loc[(summary.analysis_level == "Single factor") & (summary.dimension == "Direction")]
    timing_rows = summary.loc[(summary.analysis_level == "Single factor") & (summary.dimension == "Setup/BOS timing")]
    report = build_report(
        baseline=baseline,
        direction_rows=direction_rows,
        timing_rows=timing_rows,
        best=best,
        worst=worst,
        stability=stability,
        complements=complements,
        classification=classification,
    )

    features.to_csv(output / "trade_archetype_features.csv", index=False)
    summary.to_csv(output / "archetype_summary.csv", index=False)
    stability.to_csv(output / "archetype_year_stability.csv", index=False)
    complements.to_csv(output / "archetype_complements.csv", index=False)
    cumulative.to_csv(output / "archetype_cumulative_curves.csv", index=False)
    reconciliation.to_csv(output / "baseline_trade_reconciliation.csv", index=False)
    pd.DataFrame([{"baseline": "705-trade development", **baseline}]).to_csv(output / "baseline_summary.csv", index=False)
    (output / "TRADE_ARCHETYPE_DECOMPOSITION.md").write_text(report)

    root = project_root or Path.cwd()
    frozen_paths = [
        root / "phase16/config.py",
        root / "phase16/entry_models.py",
        root / "phase16/setup_engine.py",
        root / "phase16/trade_engine.py",
        root / "outputs/CRT_Core_RETEST_GATED_LIVE.pine",
    ]
    manifest = {
        "baseline_reproduced": True,
        "trades_verified": 705,
        "archived_field_mismatches": int(reconciliation.mismatches.sum()),
        "development_only": True,
        "new_data_downloaded": False,
        "unseen_oos_accessed": False,
        "pine_modified": False,
        "window": {"start": start, "end": end},
        "bars_in_window": int(current_result.diagnostics.get("Bars In Window", 0)),
        "baseline": baseline,
        "adequate_N_family_tests": len(complements),
        "FDR_survivors": int(complements.FDR_significant_0_05.sum()),
        "robust_positive_families": int(complements.robust_positive_family.sum()),
        "robust_negative_families": int(complements.robust_negative_family.sum()),
        "best_family_id": str(best.family_id),
        "worst_family_id": str(worst.family_id),
        "classification": classification,
        "cost_assumption": {"round_turn_USD": ROUND_TURN_COST_USD, "NQ_USD_per_point": NQ_DOLLARS_PER_POINT},
        "frozen_sha256": {str(path.relative_to(root)): _file_sha256(path) for path in frozen_paths},
    }
    (output / "analysis_manifest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n")
    return manifest
