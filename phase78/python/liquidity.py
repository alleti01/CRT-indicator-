"""Causal pre-window liquidity map for Silver Bullet."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import numpy as np
import pandas as pd

from .config import EQ_TOL_PRIMARY, PIVOT_LEFT, PIVOT_RIGHT

Side = Literal["BUY_SIDE", "SELL_SIDE"]


@dataclass
class LiquidityLevel:
    level_type: str
    level_price: float
    side: Side
    created_at: pd.Timestamp
    confirmed_at: pd.Timestamp
    known_at: pd.Timestamp


@dataclass
class LiquidityMap:
    levels: list[LiquidityLevel] = field(default_factory=list)

    def buy_side(self) -> list[LiquidityLevel]:
        return [l for l in self.levels if l.side == "BUY_SIDE"]

    def sell_side(self) -> list[LiquidityLevel]:
        return [l for l in self.levels if l.side == "SELL_SIDE"]


from .swings import causal_pivot_highs_lows
def _equal_clusters(
    prices: list[tuple[int, float, pd.Timestamp]],
    atr: float,
    tol_atr: float,
    *,
    level_type: str,
    side: Side,
) -> list[LiquidityLevel]:
    if not prices or not np.isfinite(atr) or atr <= 0:
        return []
    tol = max(tol_atr * atr, 1.0)
    out: list[LiquidityLevel] = []
    used = set()
    for i, (idx_i, px_i, conf_i) in enumerate(prices):
        if i in used:
            continue
        cluster = [(idx_i, px_i, conf_i)]
        used.add(i)
        for j in range(i + 1, len(prices)):
            if j in used:
                continue
            idx_j, px_j, conf_j = prices[j]
            if abs(px_j - px_i) <= tol:
                cluster.append((idx_j, px_j, conf_j))
                used.add(j)
        if len(cluster) >= 2:
            avg_px = float(np.mean([c[1] for c in cluster]))
            first = min(cluster, key=lambda x: x[0])
            last = max(cluster, key=lambda x: x[2])
            out.append(
                LiquidityLevel(
                    level_type=level_type,
                    level_price=avg_px,
                    side=side,
                    created_at=first[2],
                    confirmed_at=last[2],
                    known_at=last[2],
                )
            )
    return out


def build_equal_levels(
    swing_highs: list[tuple[int, float, pd.Timestamp]],
    swing_lows: list[tuple[int, float, pd.Timestamp]],
    atr: float,
    tol_atr: float = EQ_TOL_PRIMARY,
) -> list[LiquidityLevel]:
    eq_h = _equal_clusters(swing_highs, atr, tol_atr, level_type="EQUAL_HIGHS", side="BUY_SIDE")
    eq_l = _equal_clusters(swing_lows, atr, tol_atr, level_type="EQUAL_LOWS", side="SELL_SIDE")
    return eq_h + eq_l


def session_levels_before(
    df: pd.DataFrame,
    window_start_utc: pd.Timestamp,
    calendar_date: date,
) -> list[LiquidityLevel]:
    """Freeze session / overnight / prior RTH levels known before window."""
    ts_et = df["ts_et"]
    mask = df.index < window_start_utc
    if not mask.any():
        return []
    sub = df.loc[mask]
    sub_et = ts_et.loc[mask]
    levels: list[LiquidityLevel] = []

    # Prior completed RTH session (previous weekday)
    rth_mask = (sub_et.dt.time >= pd.Timestamp("09:30").time()) & (sub_et.dt.time < pd.Timestamp("16:00").time())
    rth_days = sorted(set(sub_et[rth_mask].dt.date))
    if rth_days:
        prev_day = rth_days[-1]
        day_mask = sub_et.dt.date == prev_day
        day_rth = day_mask & rth_mask
        if day_rth.any():
            hi = float(sub.loc[day_rth, "high"].max())
            lo = float(sub.loc[day_rth, "low"].min())
            last_ts = sub.index[day_rth][-1]
            levels.append(
                LiquidityLevel("PRIOR_SESSION_HIGH", hi, "BUY_SIDE", last_ts, last_ts, window_start_utc)
            )
            levels.append(
                LiquidityLevel("PRIOR_SESSION_LOW", lo, "SELL_SIDE", last_ts, last_ts, window_start_utc)
            )

    # Overnight for current calendar date (18:00 prior → window start)
    today = calendar_date
    overnight_mask = sub_et.dt.date == today
    overnight_mask &= (sub_et.dt.time < pd.Timestamp("09:30").time()) | (sub_et.dt.time >= pd.Timestamp("18:00").time())
    if overnight_mask.any():
        hi = float(sub.loc[overnight_mask, "high"].max())
        lo = float(sub.loc[overnight_mask, "low"].min())
        last_ts = sub.index[overnight_mask][-1]
        levels.append(LiquidityLevel("OVERNIGHT_HIGH", hi, "BUY_SIDE", last_ts, last_ts, window_start_utc))
        levels.append(LiquidityLevel("OVERNIGHT_LOW", lo, "SELL_SIDE", last_ts, last_ts, window_start_utc))

    # Current session developing H/L before window
    today_mask = sub_et.dt.date == today
    if today_mask.any():
        hi = float(sub.loc[today_mask, "high"].max())
        lo = float(sub.loc[today_mask, "low"].min())
        last_ts = sub.index[today_mask][-1]
        levels.append(
            LiquidityLevel("SESSION_HIGH_PRE_WINDOW", hi, "BUY_SIDE", last_ts, last_ts, window_start_utc)
        )
        levels.append(
            LiquidityLevel("SESSION_LOW_PRE_WINDOW", lo, "SELL_SIDE", last_ts, last_ts, window_start_utc)
        )

    return levels


from .session_cache import session_levels_cached


def freeze_liquidity_map(
    df: pd.DataFrame,
    index: pd.DatetimeIndex,
    window_start_idx: int,
    calendar_date: date,
    swing_highs: list[tuple[int, float, int]],
    swing_lows: list[tuple[int, float, int]],
    atr_at_window: float,
    session_cache: dict | None = None,
) -> LiquidityMap:
    window_start_utc = index[window_start_idx]
    levels: list[LiquidityLevel] = []
    if session_cache is not None:
        for ltype, side, px in session_levels_cached(df, window_start_utc, calendar_date, session_cache):
            levels.append(
                LiquidityLevel(
                    ltype, px, side, window_start_utc, window_start_utc, window_start_utc  # type: ignore[arg-type]
                )
            )
    else:
        levels.extend(session_levels_before(df, window_start_utc, calendar_date))
    for _, px, conf_i in swing_highs[-150:]:
        conf = index[conf_i]
        levels.append(LiquidityLevel("SWING_HIGH", px, "BUY_SIDE", conf, conf, conf))
    for _, px, conf_i in swing_lows[-150:]:
        conf = index[conf_i]
        levels.append(LiquidityLevel("SWING_LOW", px, "SELL_SIDE", conf, conf, conf))
    sh_ts = [(p, px, index[c]) for p, px, c in swing_highs[-80:]]
    sl_ts = [(p, px, index[c]) for p, px, c in swing_lows[-80:]]
    levels.extend(build_equal_levels(sh_ts, sl_ts, atr_at_window))
    return LiquidityMap(levels=levels)
