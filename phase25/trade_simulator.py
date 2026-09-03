"""Causal BOS trade simulation with configurable entry/exit architecture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import BOS_RETEST_TOLERANCE_ATR, RETRACE_WINDOW_BARS


@dataclass(frozen=True)
class SimConfig:
    entry_model: str = "CURRENT"
    stop_atr: float = 1.5
    target_r: float = 2.0
    max_bars: int = 12
    management: str = "FIXED"
    trail_atr: float = 1.0


@dataclass
class SimResult:
    signal_id: int
    filled: bool
    entry_timestamp: Optional[pd.Timestamp]
    entry_price: Optional[float]
    exit_timestamp: Optional[pd.Timestamp]
    exit_price: Optional[float]
    stop_price: Optional[float]
    result_R: float
    exit_reason: str
    mfe_r: float
    mae_r: float
    bars_in_trade: int
    entry_model: str


def _direction_code(direction: str) -> int:
    return 1 if direction == "Long" else -1


def _get(row, key: str):
    if hasattr(row, key):
        return getattr(row, key)
    return row[key]


def resolve_entry(
    signal,
    market: pd.DataFrame,
    pos_map: Dict[pd.Timestamp, int],
    entry_model: str,
) -> Tuple[bool, Optional[int], Optional[float], Optional[pd.Timestamp]]:
    signal_ts = _get(signal, "entry_timestamp")
    if signal_ts not in pos_map:
        return False, None, None, None
    sig_i = pos_map[signal_ts]
    sig_bar = market.iloc[sig_i]
    direction = _direction_code(str(_get(signal, "direction")))
    atr = float(sig_bar["atr"]) if np.isfinite(sig_bar["atr"]) else 1.0
    bar_range = float(sig_bar["high"] - sig_bar["low"])

    if entry_model == "CURRENT":
        return True, sig_i, float(sig_bar["close"]), signal_ts

    if sig_i + 1 >= len(market):
        return False, None, None, None

    if entry_model == "NEXT_OPEN":
        nxt = market.iloc[sig_i + 1]
        return True, sig_i + 1, float(nxt["open"]), market.index[sig_i + 1]

    if entry_model == "NEXT_CLOSE":
        nxt = market.iloc[sig_i + 1]
        return True, sig_i + 1, float(nxt["close"]), market.index[sig_i + 1]

    if entry_model in {"RETRACE_25", "RETRACE_50"}:
        frac = 0.25 if entry_model == "RETRACE_25" else 0.50
        if direction == 1:
            limit = float(sig_bar["close"]) - frac * bar_range
        else:
            limit = float(sig_bar["close"]) + frac * bar_range
        for j in range(sig_i + 1, min(sig_i + 1 + RETRACE_WINDOW_BARS, len(market))):
            bar = market.iloc[j]
            if bar["low"] <= limit <= bar["high"]:
                return True, j, limit, market.index[j]
        return False, None, None, None

    if entry_model == "BOS_RETEST":
        if sig_i == 0:
            return False, None, None, None
        prior = market.iloc[sig_i - 1]
        bos_level = float(prior["high"]) if direction == 1 else float(prior["low"])
        tol = BOS_RETEST_TOLERANCE_ATR * atr
        for j in range(sig_i + 1, min(sig_i + 1 + RETRACE_WINDOW_BARS, len(market))):
            bar = market.iloc[j]
            if direction == 1 and bar["low"] <= bos_level + tol:
                return True, j, float(bar["close"]), market.index[j]
            if direction == -1 and bar["high"] >= bos_level - tol:
                return True, j, float(bar["close"]), market.index[j]
        return False, None, None, None

    return False, None, None, None


def simulate_trade(
    signal,
    market: pd.DataFrame,
    pos_map: Dict[pd.Timestamp, int],
    config: SimConfig,
) -> SimResult:
    filled, entry_i, entry_price, entry_ts = resolve_entry(
        signal, market, pos_map, config.entry_model
    )
    sid = int(_get(signal, "signal_id"))
    if not filled or entry_i is None or entry_price is None or entry_ts is None:
        return SimResult(
            signal_id=sid,
            filled=False,
            entry_timestamp=None,
            entry_price=None,
            exit_timestamp=None,
            exit_price=None,
            stop_price=None,
            result_R=0.0,
            exit_reason="UNFILLED",
            mfe_r=0.0,
            mae_r=0.0,
            bars_in_trade=0,
            entry_model=config.entry_model,
        )

    direction = _direction_code(str(_get(signal, "direction")))
    entry_bar = market.iloc[entry_i]
    atr = float(entry_bar["atr"]) if np.isfinite(entry_bar["atr"]) else 1.0
    risk = config.stop_atr * atr
    stop = entry_price - risk if direction == 1 else entry_price + risk
    target = entry_price + config.target_r * risk if direction == 1 else entry_price - config.target_r * risk

    remaining_frac = 1.0
    realized_r = 0.0
    mfe_r = 0.0
    mae_r = 0.0
    active_stop = stop
    be_active = False
    trail_active = False
    partial_taken = False
    exit_ts = entry_ts
    exit_price = entry_price
    exit_reason = "DATA_END"
    elapsed = 0

    for elapsed, j in enumerate(range(entry_i + 1, len(market)), start=1):
        bar = market.iloc[j]
        hi, lo, close = float(bar["high"]), float(bar["low"]), float(bar["close"])
        ts = market.index[j]

        if direction == 1:
            bar_mfe = (hi - entry_price) / risk if risk > 0 else 0.0
            bar_mae = (entry_price - lo) / risk if risk > 0 else 0.0
        else:
            bar_mfe = (entry_price - lo) / risk if risk > 0 else 0.0
            bar_mae = (hi - entry_price) / risk if risk > 0 else 0.0
        mfe_r = max(mfe_r, bar_mfe)
        mae_r = max(mae_r, bar_mae)

        if config.management == "BE_AFTER_1R" and not be_active and mfe_r >= 1.0:
            active_stop = entry_price
            be_active = True
        if config.management in {"PARTIAL_1R", "PARTIAL_1R_BE"} and not partial_taken and mfe_r >= 1.0:
            realized_r += 0.5 * 1.0
            remaining_frac = 0.5
            partial_taken = True
            if config.management == "PARTIAL_1R_BE":
                active_stop = entry_price
        if config.management == "TRAIL_AFTER_1R" and mfe_r >= 1.0:
            trail_active = True
        if trail_active:
            if direction == 1:
                active_stop = max(active_stop, close - config.trail_atr * atr)
            else:
                active_stop = min(active_stop, close + config.trail_atr * atr)

        hit_stop = (lo <= active_stop) if direction == 1 else (hi >= active_stop)
        hit_target = (hi >= target) if direction == 1 else (lo <= target)

        if hit_stop:
            stop_r = (active_stop - entry_price) / risk if direction == 1 else (entry_price - active_stop) / risk
            realized_r += remaining_frac * stop_r
            exit_ts, exit_price, exit_reason = ts, active_stop, "STOP"
            break
        if hit_target:
            realized_r += remaining_frac * config.target_r
            exit_ts, exit_price, exit_reason = ts, target, "TARGET"
            break
        if elapsed >= config.max_bars:
            time_r = (close - entry_price) / risk if direction == 1 else (entry_price - close) / risk
            realized_r += remaining_frac * time_r
            exit_ts, exit_price, exit_reason = ts, close, "TIME"
            break

    return SimResult(
        signal_id=sid,
        filled=True,
        entry_timestamp=entry_ts,
        entry_price=entry_price,
        exit_timestamp=exit_ts,
        exit_price=exit_price,
        stop_price=float(stop),
        result_R=float(realized_r),
        exit_reason=exit_reason,
        mfe_r=float(mfe_r),
        mae_r=float(mae_r),
        bars_in_trade=elapsed,
        entry_model=config.entry_model,
    )


def first_passage_probs(
    direction: str,
    entry: float,
    risk: float,
    highs: np.ndarray,
    lows: np.ndarray,
    profit_levels: Tuple[float, ...],
    loss_levels: Tuple[float, ...],
) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    d = _direction_code(direction)
    for pl in profit_levels:
        for ll in loss_levels:
            key = f"p_{pl}R_before_{ll}R"
            hit = None
            for hi, lo in zip(highs, lows):
                if d == 1:
                    up = (hi - entry) / risk >= pl
                    dn = (entry - lo) / risk >= ll
                else:
                    up = (entry - lo) / risk >= pl
                    dn = (hi - entry) / risk >= ll
                if up and not dn:
                    hit = True
                    break
                if dn and not up:
                    hit = False
                    break
                if up and dn:
                    hit = False
                    break
            out[key] = bool(hit) if hit is not None else False
    return out
