"""Reversal entry models for Phase 33."""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from phase29.config import BOS_RETEST_TOLERANCE_ATR, RETRACE_WINDOW_BARS
from phase29.simulator import SimConfig, SimResult, _direction_code, _get, simulate_trade


def _sim_entry_model(entry_model: str) -> str:
    if entry_model == "CONFIRM_CLOSE":
        return "CURRENT"
    if entry_model == "NEXT_CLOSE":
        return "NEXT_CLOSE"
    if entry_model == "BOS_RETEST":
        return "BOS_RETEST"
    if entry_model == "RECLAIM_RETEST":
        return "RECLAIM_RETEST"
    raise ValueError(f"Unknown entry model: {entry_model}")


def resolve_reclaim_retest(
    signal,
    market: pd.DataFrame,
    pos_map: Dict[pd.Timestamp, int],
) -> Tuple[bool, Optional[int], Optional[float], Optional[pd.Timestamp]]:
    signal_ts = pd.Timestamp(_get(signal, "entry_timestamp"))
    if signal_ts not in pos_map:
        return False, None, None, None
    sig_i = pos_map[signal_ts]
    direction = _direction_code(str(_get(signal, "direction")))
    reclaim_level = float(_get(signal, "reclaim_level"))
    atr = float(market.iloc[sig_i]["atr"]) if np.isfinite(market.iloc[sig_i]["atr"]) else 1.0
    tol = BOS_RETEST_TOLERANCE_ATR * atr
    for j in range(sig_i + 1, min(sig_i + 1 + RETRACE_WINDOW_BARS, len(market))):
        bar = market.iloc[j]
        if direction == 1 and float(bar["low"]) <= reclaim_level + tol:
            return True, j, float(min(reclaim_level + tol, bar["close"])), market.index[j]
        if direction == -1 and float(bar["high"]) >= reclaim_level - tol:
            return True, j, float(max(reclaim_level - tol, bar["close"])), market.index[j]
    return False, None, None, None


def simulate_reversal_trade(
    signal,
    market: pd.DataFrame,
    pos_map: Dict[pd.Timestamp, int],
    config_row: dict,
) -> SimResult:
    entry_model = str(config_row["entry_model"])
    sim_model = _sim_entry_model(entry_model)
    cfg = SimConfig(
        entry_model=sim_model,
        stop_atr=float(config_row["stop_atr"]),
        target_r=float(config_row["target_r"]),
        max_bars=int(config_row["max_bars"]),
        management=str(config_row.get("management", "FIXED")),
    )
    if entry_model != "RECLAIM_RETEST":
        return simulate_trade(signal, market, pos_map, cfg)
    sid = int(_get(signal, "signal_id"))
    filled, entry_i, entry_price, entry_ts = resolve_reclaim_retest(signal, market, pos_map)
    if not filled or entry_i is None or entry_price is None or entry_ts is None:
        return SimResult(sid, False, None, None, None, None, None, 0.0, "UNFILLED", 0.0, 0.0, 0, entry_model)
    direction = _direction_code(str(_get(signal, "direction")))
    entry_bar = market.iloc[entry_i]
    atr = float(entry_bar["atr"]) if np.isfinite(entry_bar["atr"]) else 1.0
    risk = cfg.stop_atr * atr
    stop = entry_price - risk if direction == 1 else entry_price + risk
    target = entry_price + cfg.target_r * risk if direction == 1 else entry_price - cfg.target_r * risk
    remaining_frac = 1.0
    realized_r = 0.0
    mfe_r = mae_r = 0.0
    active_stop = stop
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
        hit_stop = lo <= active_stop if direction == 1 else hi >= active_stop
        hit_target = hi >= target if direction == 1 else lo <= target
        if hit_stop:
            stop_r = (active_stop - entry_price) / risk if direction == 1 else (entry_price - active_stop) / risk
            realized_r += remaining_frac * stop_r
            exit_ts, exit_price, exit_reason = ts, active_stop, "STOP"
            break
        if hit_target:
            realized_r += remaining_frac * cfg.target_r
            exit_ts, exit_price, exit_reason = ts, target, "TARGET"
            break
        if elapsed >= cfg.max_bars:
            time_r = (close - entry_price) / risk if direction == 1 else (entry_price - close) / risk
            realized_r += remaining_frac * time_r
            exit_ts, exit_price, exit_reason = ts, close, "TIME"
            break
    return SimResult(
        sid,
        True,
        entry_ts,
        entry_price,
        exit_ts,
        exit_price,
        float(stop),
        float(realized_r),
        exit_reason,
        float(mfe_r),
        float(mae_r),
        elapsed,
        entry_model,
    )


def simulate_all_reversal(
    signals: pd.DataFrame,
    market: pd.DataFrame,
    config_row: dict,
) -> pd.DataFrame:
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    rows = [simulate_reversal_trade(row, market, pos_map, config_row).__dict__ for row in signals.itertuples(index=False)]
    out = pd.DataFrame(rows)
    meta_cols = [
        c
        for c in (
            "signal_id",
            "direction",
            "entry_timestamp",
            "bos_timestamp",
            "architecture",
            "event_id",
            "failure_definition",
            "displacement_timestamp",
            "displacement_direction",
            "reclaim_level",
        )
        if c in signals.columns
    ]
    if meta_cols:
        out = out.merge(signals[meta_cols], on="signal_id", how="left", suffixes=("", "_sig"))
    return out
