"""Incremental causal E1–E16 detector (mirrors phase53/research/events.py)."""

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
from phase53.research.events import generate_all_events


class S54EventDetector:
    """Bar-by-bar event detector using frozen Phase53 logic."""

    def __init__(self, market: pd.DataFrame, *, swing: int = DEFAULT_SWING, start_i: int = 500):
        self.market = market
        self.swing = swing
        self.start_i = start_i
        self._counter = 0
        hi = market["high"].values.astype(float)
        lo = market["low"].values.astype(float)
        cl = market["close"].values.astype(float)
        op = market["open"].values.astype(float)
        self.hi, self.lo, self.cl, self.op = hi, lo, cl, op
        self.idx = market.index
        self.n = len(market)
        self.avg_body = pd.Series(np.abs(cl - op)).rolling(20, min_periods=20).mean().values
        self.sh_arr = precompute_swing_highs(hi, swing)
        self.sl_arr = precompute_swing_lows(lo, swing)
        self.sh1, self.sh2 = precompute_last2_swing_highs(hi, swing)
        self.sl1, self.sl2 = precompute_last2_swing_lows(lo, swing)
        self.beyond_sh = False
        self.beyond_sl = False
        self.armed_long = None
        self.armed_short = None
        self.in_range = True
        self.last_rh = np.nan
        self.last_rl = np.nan
        self.struct_state = 0
        self.current_i = start_i - 1

    def step(self, i: int) -> list[dict]:
        if i < self.start_i or i >= self.n - 61:
            return []
        self.current_i = i
        rows: list[dict] = []
        sh, sl = self.sh_arr[i], self.sl_arr[i]
        if not np.isfinite(sh) and not np.isfinite(sl):
            return []

        def emit(etype: str, direction: str, level: float) -> None:
            self._counter += 1
            rows.append(
                {
                    "entry_i": i,
                    "timestamp_ct": self.idx[i],
                    "direction": direction,
                    "event_type": etype,
                    "structure_level": level,
                    "event_id": f"P53-{self._counter:07d}",
                }
            )

        cl, hi, lo, op = self.cl[i], self.hi[i], self.lo[i], self.op[i]

        if np.isfinite(sh):
            if cl <= sh:
                self.beyond_sh = False
            elif not self.beyond_sh:
                emit("E1", "LONG", float(sh))
                self.beyond_sh = True
                self.struct_state = 1
        if np.isfinite(sl):
            if cl >= sl:
                self.beyond_sl = False
            elif not self.beyond_sl:
                emit("E2", "SHORT", float(sl))
                self.beyond_sl = True
                self.struct_state = -1

        if np.isfinite(self.sh1[i]) and np.isfinite(self.sh2[i]) and self.sh1[i] < self.sh2[i]:
            lvl = self.sh1[i]
            if cl <= lvl:
                self.armed_long = None
            elif self.armed_long != lvl:
                emit("E3", "LONG", float(lvl))
                self.armed_long = lvl
                self.struct_state = 1
        if np.isfinite(self.sl1[i]) and np.isfinite(self.sl2[i]) and self.sl1[i] > self.sl2[i]:
            lvl = self.sl1[i]
            if cl >= lvl:
                self.armed_short = None
            elif self.armed_short != lvl:
                emit("E4", "SHORT", float(lvl))
                self.armed_short = lvl
                self.struct_state = -1

        if i >= 2 and np.isfinite(sl):
            if self.lo[i - 1] < sl and cl > sl and cl > op:
                emit("E5", "LONG", float(sl))
        if i >= 2 and np.isfinite(sh):
            if self.hi[i - 1] > sh and cl < sh and cl < op:
                emit("E6", "SHORT", float(sh))

        ab = self.avg_body[i]
        if np.isfinite(ab) and abs(cl - op) > DISPLACEMENT_BODY_MULT * ab:
            if np.isfinite(sh) and cl > sh and not self.beyond_sh:
                emit("E7", "LONG", float(sh))
            if np.isfinite(sl) and cl < sl and not self.beyond_sl:
                emit("E8", "SHORT", float(sl))

        if np.isfinite(self.sh1[i]) and np.isfinite(self.sh2[i]) and self.sh1[i] > self.sh2[i] and np.isfinite(self.sl1[i]) and np.isfinite(sh):
            mid = (self.sh1[i] + self.sl1[i]) / 2.0
            if lo <= mid <= hi and cl > sh:
                emit("E9", "LONG", float(sh))
        if np.isfinite(self.sl1[i]) and np.isfinite(self.sl2[i]) and self.sl1[i] < self.sl2[i] and np.isfinite(self.sh1[i]) and np.isfinite(sl):
            mid = (self.sh1[i] + self.sl1[i]) / 2.0
            if lo <= mid <= hi and cl < sl:
                emit("E10", "SHORT", float(sl))

        lb = 30
        if i >= lb:
            rh = np.max(self.hi[i - lb : i])
            rl = np.min(self.lo[i - lb : i])
            if rl <= cl <= rh:
                self.in_range = True
            elif cl > rh and self.in_range:
                emit("E11", "LONG", float(rh))
                self.in_range = False
            elif cl < rl and self.in_range:
                emit("E12", "SHORT", float(rl))
                self.in_range = False
            if hi > rh and cl < rh and self.last_rh != rh:
                emit("E13", "LONG", float(rh))
                self.last_rh = rh
            if lo < rl and cl > rl and self.last_rl != rl:
                emit("E14", "SHORT", float(rl))
                self.last_rl = rl

        atr_i = float(self.market.iloc[i].get("atr", np.nan)) if "atr" in self.market.columns else np.nan
        if i >= 5 and np.isfinite(atr_i) and atr_i > 0:
            ext_dn = (self.cl[i - 5] - cl) / atr_i
            if self.struct_state <= 0 and ext_dn >= 1.5 and np.isfinite(sh) and cl > sh:
                emit("E15", "LONG", float(sh))
            ext_up = (cl - self.cl[i - 5]) / atr_i
            if self.struct_state >= 0 and ext_up >= 1.5 and np.isfinite(sl) and cl < sl:
                emit("E16", "SHORT", float(sl))
        return rows

    def run_all(self) -> pd.DataFrame:
        all_rows: list[dict] = []
        for i in range(self.start_i, self.n - 61):
            all_rows.extend(self.step(i))
        return pd.DataFrame(all_rows)


def batch_events(market: pd.DataFrame) -> pd.DataFrame:
    return generate_all_events(market)
