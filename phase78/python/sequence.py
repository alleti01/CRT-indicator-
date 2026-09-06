"""Silver Bullet canonical sequence state machine — strictly causal."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import numpy as np
import pandas as pd

from .config import (
    DISPLACEMENT_MAX_BARS,
    DISPLACEMENT_PRIMARY,
    ENTRY_DELAY_BARS,
    ENTRY_PRIMARY,
    FVG_MAX_BARS_AFTER_MSS,
    MSS_MAX_BARS_AFTER_DISP,
    MSS_PRIMARY,
)
from .liquidity import LiquidityLevel, LiquidityMap

Direction = Literal["LONG", "SHORT"]


class SetupState(str, Enum):
    WAIT_WINDOW = "WAIT_WINDOW"
    WAIT_SWEEP = "WAIT_SWEEP"
    SWEEP_DETECTED = "SWEEP_DETECTED"
    WAIT_DISPLACEMENT = "WAIT_DISPLACEMENT"
    WAIT_MSS = "WAIT_MSS"
    WAIT_FVG = "WAIT_FVG"
    WAIT_RETRACE = "WAIT_RETRACE"
    ENTRY_READY = "ENTRY_READY"
    ENTERED = "ENTERED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


@dataclass
class FVG:
    direction: Direction
    created_at: pd.Timestamp
    low: float
    high: float
    bar_idx: int

    @property
    def midpoint(self) -> float:
        return (self.low + self.high) / 2.0


@dataclass
class SetupRecord:
    calendar_date: object
    window_id: str
    state: SetupState = SetupState.WAIT_SWEEP
    direction: Direction | None = None
    liquidity_type: str = ""
    liquidity_price: float = np.nan
    sweep_time: pd.Timestamp | None = None
    sweep_extreme: float = np.nan
    sweep_distance_points: float = np.nan
    displacement_time: pd.Timestamp | None = None
    displacement_atr: float = np.nan
    mss_time: pd.Timestamp | None = None
    mss_level: float = np.nan
    fvg: FVG | None = None
    retrace_time: pd.Timestamp | None = None
    entry_time: pd.Timestamp | None = None
    entry_price: float = np.nan
    entry_location: str = ""
    stop: float = np.nan
    expire_reason: str = ""
    funnel_flags: dict = field(default_factory=dict)


def _detect_sweep(
    high: float, low: float, liq: LiquidityLevel
) -> tuple[bool, float, float]:
    """Return (swept, extreme, distance)."""
    if liq.side == "BUY_SIDE" and high > liq.level_price:
        return True, high, high - liq.level_price
    if liq.side == "SELL_SIDE" and low < liq.level_price:
        return True, low, liq.level_price - low
    return False, np.nan, np.nan


def _displacement_ok(
    direction: Direction,
    sweep_extreme: float,
    close: float,
    atr: float,
    min_atr: float = DISPLACEMENT_PRIMARY,
) -> tuple[bool, float]:
    if not np.isfinite(atr) or atr <= 0:
        return False, np.nan
    if direction == "SHORT":
        move = sweep_extreme - close
    else:
        move = close - sweep_extreme
    disp_atr = move / atr
    return disp_atr >= min_atr, disp_atr


def _mss_ok(
    direction: Direction,
    close: float,
    lows: np.ndarray,
    highs: np.ndarray,
    bar_idx: int,
    lookback: int = MSS_PRIMARY,
) -> tuple[bool, float]:
    if bar_idx < lookback:
        return False, np.nan
    if direction == "SHORT":
        struct = float(np.min(lows[bar_idx - lookback : bar_idx]))
        return close < struct, struct
    struct = float(np.max(highs[bar_idx - lookback : bar_idx]))
    return close > struct, struct


def _detect_fvg(
    direction: Direction,
    highs: np.ndarray,
    lows: np.ndarray,
    bar_idx: int,
) -> FVG | None:
    if bar_idx < 2:
        return None
    h1, l1 = highs[bar_idx - 2], lows[bar_idx - 2]
    h3, l3 = highs[bar_idx], lows[bar_idx]
    ts = None  # filled by caller
    if direction == "LONG" and l3 > h1:
        return FVG("LONG", ts, float(h1), float(l3), bar_idx)  # type: ignore[arg-type]
    if direction == "SHORT" and h3 < l1:
        return FVG("SHORT", ts, float(h3), float(l1), bar_idx)  # type: ignore[arg-type]
    return None


def scan_window(
    df_slice: pd.DataFrame,
    global_indices: np.ndarray,
    liq_map: LiquidityMap,
    calendar_date: object,
    window_id: str,
    window_end_utc: pd.Timestamp,
    entry_mode: str = ENTRY_PRIMARY,
) -> tuple[list[SetupRecord], dict]:
    """Scan one SB window; return all executable entries + funnel dict."""
    funnel = {
        "window": 1,
        "sweep": 0,
        "displacement": 0,
        "mss": 0,
        "fvg": 0,
        "retrace": 0,
        "entry": 0,
    }
    entries: list[SetupRecord] = []
    if len(df_slice) == 0:
        return entries, funnel

    highs = df_slice["high"].values
    lows = df_slice["low"].values
    closes = df_slice["close"].values
    opens = df_slice["open"].values
    atrs = df_slice["atr"].values
    index = df_slice.index

    best_partial: SetupRecord | None = None
    active: SetupRecord | None = None
    swept_levels: set[tuple[str, float]] = set()
    max_funnel = dict(funnel)

    for local_i in range(len(df_slice)):
        ts = index[local_i]
        if ts > window_end_utc:
            break
        h, l, c, atr = highs[local_i], lows[local_i], closes[local_i], atrs[local_i]

        # Try new sweeps if no active setup past sweep
        if active is None or active.state in (SetupState.WAIT_SWEEP, SetupState.EXPIRED, SetupState.INVALIDATED):
            for liq in liq_map.levels:
                key = (liq.level_type, liq.level_price)
                if key in swept_levels:
                    continue
                swept, extreme, dist = _detect_sweep(h, l, liq)
                if not swept:
                    continue
                swept_levels.add(key)
                max_funnel["sweep"] = 1
                direction: Direction = "SHORT" if liq.side == "BUY_SIDE" else "LONG"
                active = SetupRecord(
                    calendar_date=calendar_date,
                    window_id=window_id,
                    state=SetupState.SWEEP_DETECTED,
                    direction=direction,
                    liquidity_type=liq.level_type,
                    liquidity_price=liq.level_price,
                    sweep_time=ts,
                    sweep_extreme=extreme,
                    sweep_distance_points=dist,
                )
                active.funnel_flags["sweep"] = True
                break

        if active is None:
            continue

        # Expire at window end handled after loop
        bars_since_sweep = 0
        if active.sweep_time is not None:
            bars_since_sweep = local_i - int(np.searchsorted(index, active.sweep_time))

        # Opposite sweep invalidates
        if active.direction == "SHORT":
            for liq in liq_map.sell_side():
                if l < liq.level_price and active.sweep_time and ts > active.sweep_time:
                    active.state = SetupState.INVALIDATED
                    active.expire_reason = "OPPOSITE_SWEEP"
                    break
        else:
            for liq in liq_map.buy_side():
                if h > liq.level_price and active.sweep_time and ts > active.sweep_time:
                    active.state = SetupState.INVALIDATED
                    active.expire_reason = "OPPOSITE_SWEEP"
                    break

        if active.state == SetupState.INVALIDATED:
            best_partial = _max_stage(best_partial, active)
            active = None
            continue

        # Displacement
        if active.state in (SetupState.SWEEP_DETECTED, SetupState.WAIT_DISPLACEMENT):
            active.state = SetupState.WAIT_DISPLACEMENT
            ok, disp_atr = _displacement_ok(active.direction, active.sweep_extreme, c, atr)
            if ok:
                active.state = SetupState.WAIT_MSS
                active.displacement_time = ts
                active.displacement_atr = disp_atr
                max_funnel["displacement"] = 1
                active.funnel_flags["displacement"] = True
            elif bars_since_sweep > DISPLACEMENT_MAX_BARS:
                active.state = SetupState.EXPIRED
                active.expire_reason = "NO_DISPLACEMENT"

        # MSS
        if active.state == SetupState.WAIT_MSS:
            ok, mss_lvl = _mss_ok(active.direction, c, lows, highs, local_i)
            disp_bars = 0
            if active.displacement_time is not None:
                disp_bars = local_i - int(np.searchsorted(index, active.displacement_time))
            if ok:
                active.state = SetupState.WAIT_FVG
                active.mss_time = ts
                active.mss_level = mss_lvl
                max_funnel["mss"] = 1
                active.funnel_flags["mss"] = True
            elif disp_bars > MSS_MAX_BARS_AFTER_DISP:
                active.state = SetupState.EXPIRED
                active.expire_reason = "NO_MSS"

        # FVG
        if active.state == SetupState.WAIT_FVG:
            fvg = _detect_fvg(active.direction, highs, lows, local_i)
            mss_bars = 0
            if active.mss_time is not None:
                mss_bars = local_i - int(np.searchsorted(index, active.mss_time))
            if fvg is not None:
                fvg.created_at = ts
                active.fvg = fvg
                active.state = SetupState.WAIT_RETRACE
                max_funnel["fvg"] = 1
                active.funnel_flags["fvg"] = True
            elif mss_bars > FVG_MAX_BARS_AFTER_MSS:
                active.state = SetupState.EXPIRED
                active.expire_reason = "NO_FVG"

        # Retrace / entry
        if active.state == SetupState.WAIT_RETRACE and active.fvg is not None:
            fvg = active.fvg
            touched = False
            entry_px = np.nan
            if entry_mode == "FVG_MIDPOINT":
                mid = fvg.midpoint
                if active.direction == "LONG" and l <= mid:
                    touched, entry_px = True, mid
                elif active.direction == "SHORT" and h >= mid:
                    touched, entry_px = True, mid
            else:
                if active.direction == "LONG" and l <= fvg.high:
                    touched, entry_px = True, fvg.high
                elif active.direction == "SHORT" and h >= fvg.low:
                    touched, entry_px = True, fvg.low
            if touched:
                active.retrace_time = ts
                max_funnel["retrace"] = 1
                active.funnel_flags["retrace"] = True
                # Executable T+1
                exec_i = local_i + ENTRY_DELAY_BARS
                if exec_i < len(df_slice):
                    active.entry_time = index[exec_i]
                    active.entry_price = float(opens[exec_i])
                    active.entry_location = entry_mode
                    if active.direction == "SHORT":
                        active.stop = active.sweep_extreme
                    else:
                        active.stop = active.sweep_extreme
                    active.state = SetupState.ENTERED
                    max_funnel["entry"] = 1
                    entries.append(active)
                    active = None
                    continue
                active.state = SetupState.EXPIRED
                active.expire_reason = "NO_EXECUTABLE_ENTRY"

        best_partial = _max_stage(best_partial, active)

        if active and active.state == SetupState.EXPIRED:
            best_partial = _max_stage(best_partial, active)
            active = None

    if active and active.state not in (SetupState.ENTERED,):
        if active.state != SetupState.EXPIRED:
            active.state = SetupState.EXPIRED
            active.expire_reason = active.expire_reason or "WINDOW_END"
        best_partial = _max_stage(best_partial, active)

    funnel.update(max_funnel)
    return entries, funnel


def _stage_rank(rec: SetupRecord | None) -> int:
    if rec is None:
        return -1
    order = {
        SetupState.ENTERED: 7,
        SetupState.WAIT_RETRACE: 6,
        SetupState.WAIT_FVG: 5,
        SetupState.WAIT_MSS: 4,
        SetupState.WAIT_DISPLACEMENT: 3,
        SetupState.SWEEP_DETECTED: 2,
        SetupState.WAIT_SWEEP: 1,
    }
    return order.get(rec.state, 0)


def _max_stage(a: SetupRecord | None, b: SetupRecord | None) -> SetupRecord | None:
    if _stage_rank(b) > _stage_rank(a):
        return b
    return a
