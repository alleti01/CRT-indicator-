"""Causal CRT V2 @ 15m trade simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from .config import BOS_RETEST_TOLERANCE_ATR, RETRACE_WINDOW_BARS


@dataclass(frozen=True)
class SimConfig:
    entry_model: str = "CURRENT"
    stop_atr: float = 1.5
    target_r: float = 2.0
    max_bars: int = 4
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
    return 1 if str(direction).lower() == "long" else -1


def _get(row, key: str):
    return getattr(row, key) if hasattr(row, key) else row[key]


def resolve_entry(
    signal,
    market: pd.DataFrame,
    pos_map: Dict[pd.Timestamp, int],
    entry_model: str,
) -> Tuple[bool, Optional[int], Optional[float], Optional[pd.Timestamp]]:
    signal_ts = pd.Timestamp(_get(signal, "entry_timestamp"))
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
        limit = float(sig_bar["close"]) - frac * bar_range if direction == 1 else float(sig_bar["close"]) + frac * bar_range
        for j in range(sig_i + 1, min(sig_i + 1 + RETRACE_WINDOW_BARS, len(market))):
            bar = market.iloc[j]
            if bar["low"] <= limit <= bar["high"]:
                return True, j, limit, market.index[j]
        return False, None, None, None

    if entry_model == "BOS_RETEST":
        bos_ts = _get(signal, "bos_timestamp")
        if bos_ts is None or pd.isna(bos_ts):
            return False, None, None, None
        bos_ts = pd.Timestamp(bos_ts)
        if bos_ts not in pos_map:
            return False, None, None, None
        bos_bar = market.iloc[pos_map[bos_ts]]
        bos_level = float(bos_bar.high) if direction == 1 else float(bos_bar.low)
        tol = BOS_RETEST_TOLERANCE_ATR * atr
        for j in range(sig_i + 1, min(sig_i + 1 + RETRACE_WINDOW_BARS, len(market))):
            bar = market.iloc[j]
            if direction == 1 and bar["low"] <= bos_level + tol:
                return True, j, float(min(bos_level + tol, bar["close"])), market.index[j]
            if direction == -1 and bar["high"] >= bos_level - tol:
                return True, j, float(max(bos_level - tol, bar["close"])), market.index[j]
        return False, None, None, None

    return False, None, None, None


def simulate_trade(signal, market: pd.DataFrame, pos_map: Dict[pd.Timestamp, int], config: SimConfig) -> SimResult:
    filled, entry_i, entry_price, entry_ts = resolve_entry(signal, market, pos_map, config.entry_model)
    sid = int(_get(signal, "signal_id"))
    if not filled or entry_i is None or entry_price is None or entry_ts is None:
        return SimResult(sid, False, None, None, None, None, None, 0.0, "UNFILLED", 0.0, 0.0, 0, config.entry_model)

    direction = _direction_code(str(_get(signal, "direction")))
    entry_bar = market.iloc[entry_i]
    atr = float(entry_bar["atr"]) if np.isfinite(entry_bar["atr"]) else 1.0
    risk = config.stop_atr * atr
    stop = entry_price - risk if direction == 1 else entry_price + risk
    target = entry_price + config.target_r * risk if direction == 1 else entry_price - config.target_r * risk

    remaining_frac = 1.0
    realized_r = 0.0
    mfe_r = mae_r = 0.0
    active_stop = stop
    be_active = partial_taken = trail_active = False
    exit_ts, exit_price, exit_reason = entry_ts, entry_price, "DATA_END"
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
            realized_r += 0.5
            remaining_frac = 0.5
            partial_taken = True
            if config.management == "PARTIAL_1R_BE":
                active_stop = entry_price
        if config.management == "TRAIL_AFTER_1R" and mfe_r >= 1.0:
            trail_active = True
        if trail_active:
            active_stop = max(active_stop, close - config.trail_atr * atr) if direction == 1 else min(active_stop, close + config.trail_atr * atr)

        hit_stop = lo <= active_stop if direction == 1 else hi >= active_stop
        hit_target = hi >= target if direction == 1 else lo <= target
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
        sid, True, entry_ts, entry_price, exit_ts, exit_price, float(stop), float(realized_r),
        exit_reason, float(mfe_r), float(mae_r), elapsed, config.entry_model,
    )


def first_passage_probs(direction, entry, risk, highs, lows, profit_levels, loss_levels):
    out = {}
    d = _direction_code(direction)
    for pl in profit_levels:
        for ll in loss_levels:
            key = f"P_p{pl}R_before_l{ll}R"
            hit = None
            for hi, lo in zip(highs, lows):
                up = ((hi - entry) / risk >= pl) if d == 1 else ((entry - lo) / risk >= pl)
                dn = ((entry - lo) / risk >= ll) if d == 1 else ((hi - entry) / risk >= ll)
                if up and not dn:
                    hit = True
                    break
                if dn and not up:
                    hit = False
                    break
                if up and dn:
                    hit = False
                    break
            out[key] = float(bool(hit)) if hit is not None else 0.0
    return out
