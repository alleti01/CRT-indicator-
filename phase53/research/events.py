"""Causal structural event universe E1–E16 (single-pass)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase52.research.swings import (
    precompute_last2_swing_highs,
    precompute_last2_swing_lows,
    precompute_swing_highs,
    precompute_swing_lows,
)
from phase53.config import DEFAULT_SWING, DISPLACEMENT_BODY_MULT


def generate_all_events(
    market: pd.DataFrame,
    *,
    swing: int = DEFAULT_SWING,
    start_i: int = 500,
) -> pd.DataFrame:
    hi = market["high"].values.astype(float)
    lo = market["low"].values.astype(float)
    cl = market["close"].values.astype(float)
    op = market["open"].values.astype(float)
    idx = market.index
    n = len(market)
    avg_body = pd.Series(np.abs(cl - op)).rolling(20, min_periods=20).mean().values

    sh_arr = precompute_swing_highs(hi, swing)
    sl_arr = precompute_swing_lows(lo, swing)
    sh1, sh2 = precompute_last2_swing_highs(hi, swing)
    sl1, sl2 = precompute_last2_swing_lows(lo, swing)

    rows: list[dict] = []
    beyond_sh = beyond_sl = False
    armed_long = armed_short = None
    in_range = True
    last_rh = last_rl = np.nan
    struct_state = 0  # -1 bear, 0 range, 1 bull

    for i in range(start_i, n - 61):
        ts = idx[i]
        sh, sl = sh_arr[i], sl_arr[i]
        if not np.isfinite(sh) and not np.isfinite(sl):
            continue

        def emit(etype: str, direction: str, level: float) -> None:
            rows.append(
                {
                    "entry_i": i,
                    "timestamp_ct": ts,
                    "direction": direction,
                    "event_type": etype,
                    "structure_level": level,
                }
            )

        # E1/E2 micro-BOS
        if np.isfinite(sh):
            if cl[i] <= sh:
                beyond_sh = False
            elif not beyond_sh:
                emit("E1", "LONG", float(sh))
                beyond_sh = True
                struct_state = 1
        if np.isfinite(sl):
            if cl[i] >= sl:
                beyond_sl = False
            elif not beyond_sl:
                emit("E2", "SHORT", float(sl))
                beyond_sl = True
                struct_state = -1

        # E3/E4 CHoCH
        if np.isfinite(sh1[i]) and np.isfinite(sh2[i]) and sh1[i] < sh2[i]:
            lvl = sh1[i]
            if cl[i] <= lvl:
                armed_long = None
            elif armed_long != lvl:
                emit("E3", "LONG", float(lvl))
                armed_long = lvl
                struct_state = 1
        if np.isfinite(sl1[i]) and np.isfinite(sl2[i]) and sl1[i] > sl2[i]:
            lvl = sl1[i]
            if cl[i] >= lvl:
                armed_short = None
            elif armed_short != lvl:
                emit("E4", "SHORT", float(lvl))
                armed_short = lvl
                struct_state = -1

        # E5/E6 failed break + reclaim
        if i >= 2 and np.isfinite(sl):
            if lo[i - 1] < sl and cl[i] > sl and cl[i] > op[i]:
                emit("E5", "LONG", float(sl))
        if i >= 2 and np.isfinite(sh):
            if hi[i - 1] > sh and cl[i] < sh and cl[i] < op[i]:
                emit("E6", "SHORT", float(sh))

        # E7/E8 displacement + BOS
        ab = avg_body[i]
        if np.isfinite(ab) and abs(cl[i] - op[i]) > DISPLACEMENT_BODY_MULT * ab:
            if np.isfinite(sh) and cl[i] > sh and not beyond_sh:
                emit("E7", "LONG", float(sh))
            if np.isfinite(sl) and cl[i] < sl and not beyond_sl:
                emit("E8", "SHORT", float(sl))

        # E9/E10 pullback continuation
        if np.isfinite(sh1[i]) and np.isfinite(sh2[i]) and sh1[i] > sh2[i] and np.isfinite(sl1[i]) and np.isfinite(sh):
            mid = (sh1[i] + sl1[i]) / 2.0
            if lo[i] <= mid <= hi[i] and cl[i] > sh:
                emit("E9", "LONG", float(sh))
        if np.isfinite(sl1[i]) and np.isfinite(sl2[i]) and sl1[i] < sl2[i] and np.isfinite(sh1[i]) and np.isfinite(sl):
            mid = (sh1[i] + sl1[i]) / 2.0
            if lo[i] <= mid <= hi[i] and cl[i] < sl:
                emit("E10", "SHORT", float(sl))

        # E11/E12 range breakout (30-bar causal range excl current)
        lb = 30
        if i >= lb:
            rh = np.max(hi[i - lb : i])
            rl = np.min(lo[i - lb : i])
            if rl <= cl[i] <= rh:
                in_range = True
            elif cl[i] > rh and in_range:
                emit("E11", "LONG", float(rh))
                in_range = False
            elif cl[i] < rl and in_range:
                emit("E12", "SHORT", float(rl))
                in_range = False

            # E13/E14 failed range breakout
            if hi[i] > rh and cl[i] < rh and last_rh != rh:
                emit("E13", "LONG", float(rh))
                last_rh = rh
            if lo[i] < rl and cl[i] > rl and last_rl != rl:
                emit("E14", "SHORT", float(rl))
                last_rl = rl

        # E15/E16 structure flip after opposite state
        atr_i = float(market.iloc[i].get("atr", np.nan)) if "atr" in market.columns else np.nan
        if i >= 5 and np.isfinite(atr_i) and atr_i > 0:
            ext_dn = (cl[i - 5] - cl[i]) / atr_i
            if struct_state <= 0 and ext_dn >= 1.5 and np.isfinite(sh) and cl[i] > sh:
                emit("E15", "LONG", float(sh))
            ext_up = (cl[i] - cl[i - 5]) / atr_i
            if struct_state >= 0 and ext_up >= 1.5 and np.isfinite(sl) and cl[i] < sl:
                emit("E16", "SHORT", float(sl))

    df = pd.DataFrame(rows)
    if not df.empty:
        df["event_id"] = [f"P53-{j:07d}" for j in range(1, len(df) + 1)]
    return df
