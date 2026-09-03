"""Chronological bar-by-bar replay of frozen Phase 31 + Phase 33 indicator logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session
from phase16.resample import cme_session_date

from .config import (
    BOS_RETEST_TOL_ATR,
    DEDUPE_ACTIVE_BARS,
    DEDUPE_DAY_CAP,
    DEDUPE_SAME_DIR,
    P31_BODY_AVG_LEN,
    P31_BODY_MULT,
    P31_BOS_RETEST_WIN,
    P31_CL_LONG,
    P31_CL_SHORT,
    P31_MAX_HOLD_BARS,
    P31_STOP_ATR,
    P31_TARGET_R,
    P33_FAILURE_WIN,
    P33_MAX_HOLD_BARS,
    P33_RETEST_WIN,
    P33_STOP_ATR,
    P33_TARGET_R,
    RTH_SESSION,
)


def _day_key(ts: pd.Timestamp) -> str:
    return str(cme_session_date(pd.DatetimeIndex([ts]))[0])


def _close_loc(row) -> float:
    rng = float(row.high) - float(row.low)
    if rng <= 0:
        return np.nan
    return (float(row.close) - float(row.low)) / rng


def _try_bos_retest_fill(direction: int, level: float, tol: float, row) -> Tuple[bool, float]:
    if direction == 1 and float(row.low) <= level + tol:
        return True, float(min(level + tol, row.close))
    if direction == -1 and float(row.high) >= level - tol:
        return True, float(max(level - tol, row.close))
    return False, np.nan


def _midpoint_reclaimed(disp_dir: int, mid: float, close: float) -> bool:
    if disp_dir == -1:
        return close > mid
    return close < mid


@dataclass
class DedupeTracker:
    active_until: int = -1
    last_long: int = -999
    last_short: int = -999
    day_key: str = ""
    day_count: int = 0

    def reset_day_if_needed(self, ts: pd.Timestamp) -> None:
        dk = _day_key(ts)
        if dk != self.day_key:
            self.day_key = dk
            self.day_count = 0

    def pass_dedupe(self, bar_i: int, direction: int) -> bool:
        same_dir_ok = (
            bar_i - self.last_long >= DEDUPE_SAME_DIR
            if direction == 1
            else bar_i - self.last_short >= DEDUPE_SAME_DIR
        )
        active_ok = bar_i > self.active_until
        day_ok = self.day_count < DEDUPE_DAY_CAP
        return active_ok and same_dir_ok and day_ok

    def register(self, bar_i: int, direction: int, ts: pd.Timestamp) -> None:
        self.reset_day_if_needed(ts)
        self.active_until = bar_i + DEDUPE_ACTIVE_BARS
        if direction == 1:
            self.last_long = bar_i
        else:
            self.last_short = bar_i
        self.day_count += 1


@dataclass
class ContinuationMachine:
    state: str = "IDLE"
    direction: int = 0
    bos_level: float = np.nan
    tol: float = np.nan
    disp_bar: int = -1
    disp_ts: Optional[pd.Timestamp] = None
    disp_high: float = np.nan
    disp_low: float = np.nan
    deadline: int = -1
    entry_price: float = np.nan
    stop: float = np.nan
    target: float = np.nan
    held: int = 0
    retest_ts: Optional[pd.Timestamp] = None
    dedupe: DedupeTracker = field(default_factory=DedupeTracker)


@dataclass
class ReversalMachine:
    state: str = "IDLE"
    direction: int = 0
    disp_dir: int = 0
    mid: float = np.nan
    disp_bar: int = -1
    disp_ts: Optional[pd.Timestamp] = None
    disp_high: float = np.nan
    disp_low: float = np.nan
    reclaim_deadline: int = -1
    confirm_bar: int = -1
    reclaim_ts: Optional[pd.Timestamp] = None
    reclaim_level: float = np.nan
    tol: float = np.nan
    retest_deadline: int = -1
    retest_ts: Optional[pd.Timestamp] = None
    entry_price: float = np.nan
    stop: float = np.nan
    target: float = np.nan
    held: int = 0
    dedupe: DedupeTracker = field(default_factory=DedupeTracker)


def replay_market(market: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Replay frozen indicator bar-by-bar. Returns (signal_map, state_log)."""
    idx = market.index
    n = len(market)
    body = (market["close"] - market["open"]).abs()
    avg_body = body.rolling(P31_BODY_AVG_LEN, min_periods=P31_BODY_AVG_LEN).mean()

    p31 = ContinuationMachine()
    p33 = ReversalMachine()
    signals: List[dict] = []
    states: List[dict] = []
    signal_id = 0

    for i in range(n):
        ts = idx[i]
        row = market.iloc[i]
        rth = is_in_session(ts, RTH_SESSION)
        atr = float(row["atr"]) if np.isfinite(row["atr"]) else np.nan
        cl = _close_loc(row)
        b = float(body.iloc[i])
        ab = float(avg_body.iloc[i]) if i >= P31_BODY_AVG_LEN - 1 and np.isfinite(avg_body.iloc[i]) else np.nan
        body_ready = i >= P31_BODY_AVG_LEN - 1 and np.isfinite(ab)
        long_disp = bool(rth and body_ready and b > P31_BODY_MULT * ab and cl >= P31_CL_LONG)
        short_disp = bool(rth and body_ready and b > P31_BODY_MULT * ab and cl <= P31_CL_SHORT)

        l_fire = s_fire = rl_fire = rs_fire = False
        fire_entry = fire_stop = fire_target = np.nan
        fire_type = fire_dir = ""

        # ── Phase 31 management ──
        if p31.state == "ACTIVE":
            p31.held += 1
            hit_stop = (p31.direction == 1 and float(row.low) <= p31.stop) or (
                p31.direction == -1 and float(row.high) >= p31.stop
            )
            hit_tgt = (p31.direction == 1 and float(row.high) >= p31.target) or (
                p31.direction == -1 and float(row.low) <= p31.target
            )
            if hit_stop or hit_tgt or p31.held >= P31_MAX_HOLD_BARS:
                p31.state = "IDLE"
                p31.direction = 0

        elif p31.state == "WAIT":
            if i > p31.deadline:
                p31.state = "IDLE"
                p31.direction = 0
            elif i > p31.disp_bar:
                filled, px = _try_bos_retest_fill(p31.direction, p31.bos_level, p31.tol, row)
                if filled:
                    risk = P31_STOP_ATR * atr
                    p31.entry_price = px
                    p31.stop = px - risk if p31.direction == 1 else px + risk
                    p31.target = px + P31_TARGET_R * risk if p31.direction == 1 else px - P31_TARGET_R * risk
                    p31.held = 0
                    p31.state = "ACTIVE"
                    p31.retest_ts = ts
                    signal_id += 1
                    sig_type = "L" if p31.direction == 1 else "S"
                    direction = "Long" if p31.direction == 1 else "Short"
                    l_fire = p31.direction == 1
                    s_fire = p31.direction == -1
                    fire_type = sig_type
                    fire_dir = direction
                    fire_entry = px
                    fire_stop = p31.stop
                    fire_target = p31.target
                    mid = (p31.disp_high + p31.disp_low) / 2.0
                    expiry_i = min(i + P31_MAX_HOLD_BARS, n - 1)
                    signals.append(
                        {
                            "signal_id": signal_id,
                            "marker_bar_timestamp": ts,
                            "timestamp_ct": ts,
                            "bar_index": i,
                            "signal_type": sig_type,
                            "direction": direction,
                            "entry_price": px,
                            "open": float(row.open),
                            "high": float(row.high),
                            "low": float(row.low),
                            "close": float(row.close),
                            "atr": atr,
                            "source_displacement_time": p31.disp_ts,
                            "source_displacement_high": p31.disp_high,
                            "source_displacement_low": p31.disp_low,
                            "source_displacement_midpoint": mid,
                            "bos_or_reclaim_time": p31.disp_ts,
                            "bos_level": p31.bos_level,
                            "retest_time": ts,
                            "stop": p31.stop,
                            "target": p31.target,
                            "expiry_time": idx[expiry_i],
                            "architecture": "MOMENTUM_DISPLACEMENT",
                        }
                    )

        if p31.state == "IDLE":
            p31.dedupe.reset_day_if_needed(ts)
            if long_disp and p31.dedupe.pass_dedupe(i, 1):
                p31.direction = 1
                p31.bos_level = float(row.high)
                p31.tol = BOS_RETEST_TOL_ATR * atr
                p31.disp_bar = i
                p31.disp_ts = ts
                p31.disp_high = float(row.high)
                p31.disp_low = float(row.low)
                p31.deadline = i + P31_BOS_RETEST_WIN
                p31.state = "WAIT"
                p31.dedupe.register(i, 1, ts)
            elif short_disp and p31.dedupe.pass_dedupe(i, -1):
                p31.direction = -1
                p31.bos_level = float(row.low)
                p31.tol = BOS_RETEST_TOL_ATR * atr
                p31.disp_bar = i
                p31.disp_ts = ts
                p31.disp_high = float(row.high)
                p31.disp_low = float(row.low)
                p31.deadline = i + P31_BOS_RETEST_WIN
                p31.state = "WAIT"
                p31.dedupe.register(i, -1, ts)

        # ── Phase 33 management ──
        if p33.state == "ACTIVE":
            p33.held += 1
            hit_stop = (p33.direction == 1 and float(row.low) <= p33.stop) or (
                p33.direction == -1 and float(row.high) >= p33.stop
            )
            hit_tgt = (p33.direction == 1 and float(row.high) >= p33.target) or (
                p33.direction == -1 and float(row.low) <= p33.target
            )
            if hit_stop or hit_tgt or p33.held >= P33_MAX_HOLD_BARS:
                p33.state = "IDLE"
                p33.direction = 0
                p33.confirm_bar = -1

        elif p33.state == "WAIT_RETEST":
            if i > p33.retest_deadline:
                p33.state = "IDLE"
                p33.direction = 0
                p33.confirm_bar = -1
            elif i > p33.confirm_bar:
                filled, px = _try_bos_retest_fill(p33.direction, p33.reclaim_level, p33.tol, row)
                if filled:
                    risk = P33_STOP_ATR * atr
                    p33.entry_price = px
                    p33.stop = px - risk if p33.direction == 1 else px + risk
                    p33.target = px + P33_TARGET_R * risk if p33.direction == 1 else px - P33_TARGET_R * risk
                    p33.held = 0
                    p33.state = "ACTIVE"
                    p33.retest_ts = ts
                    signal_id += 1
                    sig_type = "RL" if p33.direction == 1 else "RS"
                    direction = "Long" if p33.direction == 1 else "Short"
                    rl_fire = p33.direction == 1
                    rs_fire = p33.direction == -1
                    fire_type = sig_type
                    fire_dir = direction
                    fire_entry = px
                    fire_stop = p33.stop
                    fire_target = p33.target
                    mid = (p33.disp_high + p33.disp_low) / 2.0
                    expiry_i = min(i + P33_MAX_HOLD_BARS, n - 1)
                    signals.append(
                        {
                            "signal_id": signal_id,
                            "marker_bar_timestamp": ts,
                            "timestamp_ct": ts,
                            "bar_index": i,
                            "signal_type": sig_type,
                            "direction": direction,
                            "entry_price": px,
                            "open": float(row.open),
                            "high": float(row.high),
                            "low": float(row.low),
                            "close": float(row.close),
                            "atr": atr,
                            "source_displacement_time": p33.disp_ts,
                            "source_displacement_high": p33.disp_high,
                            "source_displacement_low": p33.disp_low,
                            "source_displacement_midpoint": mid,
                            "bos_or_reclaim_time": p33.reclaim_ts,
                            "reclaim_level": p33.reclaim_level,
                            "retest_time": ts,
                            "stop": p33.stop,
                            "target": p33.target,
                            "expiry_time": idx[expiry_i],
                            "architecture": "DISPLACEMENT_FAILURE_REVERSAL",
                        }
                    )

        elif p33.state == "WAIT_RECLAIM":
            if i > p33.reclaim_deadline:
                p33.state = "IDLE"
                p33.direction = 0
                p33.confirm_bar = -1
            elif i > p33.disp_bar and _midpoint_reclaimed(p33.disp_dir, p33.mid, float(row.close)):
                p33.confirm_bar = i
                p33.reclaim_ts = ts
                p33.reclaim_level = p33.mid
                p33.tol = BOS_RETEST_TOL_ATR * atr
                p33.retest_deadline = i + P33_RETEST_WIN
                p33.state = "WAIT_RETEST"

        if p33.state == "IDLE":
            p33.dedupe.reset_day_if_needed(ts)
            if short_disp and p33.dedupe.pass_dedupe(i, 1):
                p33.disp_dir = -1
                p33.direction = 1
                p33.mid = (float(row.high) + float(row.low)) / 2.0
                p33.disp_bar = i
                p33.disp_ts = ts
                p33.disp_high = float(row.high)
                p33.disp_low = float(row.low)
                p33.reclaim_deadline = i + P33_FAILURE_WIN
                p33.confirm_bar = -1
                p33.state = "WAIT_RECLAIM"
                p33.dedupe.register(i, 1, ts)
            elif long_disp and p33.dedupe.pass_dedupe(i, -1):
                p33.disp_dir = 1
                p33.direction = -1
                p33.mid = (float(row.high) + float(row.low)) / 2.0
                p33.disp_bar = i
                p33.disp_ts = ts
                p33.disp_high = float(row.high)
                p33.disp_low = float(row.low)
                p33.reclaim_deadline = i + P33_FAILURE_WIN
                p33.confirm_bar = -1
                p33.state = "WAIT_RECLAIM"
                p33.dedupe.register(i, -1, ts)

        if rth:
            states.append(
                {
                    "timestamp": ts,
                    "bar_index": i,
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "atr": atr,
                    "continuation_state": p31.state,
                    "reversal_state": p33.state,
                    "bullish_displacement": long_disp,
                    "bearish_displacement": short_disp,
                    "bos_active": p31.state in ("WAIT", "ACTIVE"),
                    "bos_direction": p31.direction,
                    "bos_level": p31.bos_level if p31.state != "IDLE" else np.nan,
                    "retest_active": p31.state == "WAIT" or (p33.state == "WAIT_RETEST"),
                    "failure_window_active": p33.state == "WAIT_RECLAIM",
                    "midpoint_reclaimed": p33.state in ("WAIT_RETEST", "ACTIVE"),
                    "reclaim_retest_active": p33.state in ("WAIT_RETEST", "ACTIVE"),
                    "L_fire": l_fire,
                    "S_fire": s_fire,
                    "RL_fire": rl_fire,
                    "RS_fire": rs_fire,
                    "entry_price": fire_entry if (l_fire or s_fire or rl_fire or rs_fire) else np.nan,
                    "stop": fire_stop if (l_fire or s_fire or rl_fire or rs_fire) else np.nan,
                    "target": fire_target if (l_fire or s_fire or rl_fire or rs_fire) else np.nan,
                    "signal_type": fire_type if fire_type else "",
                }
            )

    sig_df = pd.DataFrame(signals)
    state_df = pd.DataFrame(states)
    return sig_df, state_df
