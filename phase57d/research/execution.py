"""Execution model — signal time vs execution time separation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase57d.config import MAX_HOLD_MIN, STOP_ATR, TARGET_R
from phase45.execution.data_1m import cost_r


class CausalExecutionModel:
    """Default: signal at bar close → entry at T+1 open."""

    def __init__(
        self,
        stop_atr: float = STOP_ATR,
        target_r: float = TARGET_R,
        max_hold_min: int = MAX_HOLD_MIN,
        tick_size: float = 0.25,
    ):
        self.stop_atr = stop_atr
        self.target_r = target_r
        self.max_hold_min = max_hold_min
        self.tick_size = tick_size

    def execute(
        self,
        signal: dict,
        bars: pd.DataFrame,
        signal_i: int,
        cost_mult: float = 1.0,
        tick_slippage: int = 0,
        direction: str | None = None,
    ) -> dict:
        n = len(bars)
        entry_i = signal_i + 1
        if entry_i >= n:
            return {**signal, "r": np.nan, "exit_reason": "NO_BAR"}

        atr = float(bars.iloc[signal_i].get("atr", bars.iloc[signal_i]["high"] - bars.iloc[signal_i]["low"]))
        entry = float(bars.iloc[entry_i]["open"]) + tick_slippage * self.tick_size
        d = direction or signal.get("direction", "LONG")
        if d in ("NEUTRAL", "UP", "DOWN"):
            d = "LONG" if d in ("LONG", "UP") else "SHORT"

        if d == "LONG":
            stop = entry - self.stop_atr * atr
            target = entry + self.target_r * (entry - stop)
        else:
            stop = entry + self.stop_atr * atr
            target = entry - self.target_r * (stop - entry)

        slip = tick_slippage * self.tick_size
        c = cost_r(entry, stop, multiplier=cost_mult)
        max_i = min(n - 1, entry_i + self.max_hold_min)

        for i in range(entry_i, max_i + 1):
            hi = float(bars.iloc[i]["high"])
            lo = float(bars.iloc[i]["low"])
            if d == "LONG":
                stop_hit = lo <= stop
                tgt_hit = hi >= target
            else:
                stop_hit = hi >= stop
                tgt_hit = lo <= target

            if stop_hit and tgt_hit:
                # Conservative: assume stop first
                r = -1.0 - c
                return {
                    **signal,
                    "execution_timestamp": bars.index[entry_i],
                    "entry_price": entry,
                    "stop_price": stop,
                    "target_price": target,
                    "exit_timestamp": bars.index[i],
                    "exit_price": stop,
                    "r": r,
                    "exit_reason": "STOP_SAME_BAR",
                }
            if stop_hit:
                return {
                    **signal,
                    "execution_timestamp": bars.index[entry_i],
                    "entry_price": entry,
                    "stop_price": stop,
                    "target_price": target,
                    "exit_timestamp": bars.index[i],
                    "exit_price": stop,
                    "r": -1.0 - c,
                    "exit_reason": "STOP",
                }
            if tgt_hit:
                return {
                    **signal,
                    "execution_timestamp": bars.index[entry_i],
                    "entry_price": entry,
                    "stop_price": stop,
                    "target_price": target,
                    "exit_timestamp": bars.index[i],
                    "exit_price": target,
                    "r": self.target_r - c,
                    "exit_reason": "TARGET",
                }

        last_close = float(bars.iloc[max_i]["close"])
        if d == "LONG":
            r = (last_close - entry) / (entry - stop) - c
        else:
            r = (entry - last_close) / (stop - entry) - c
        return {
            **signal,
            "execution_timestamp": bars.index[entry_i],
            "entry_price": entry,
            "stop_price": stop,
            "target_price": target,
            "exit_timestamp": bars.index[max_i],
            "exit_price": last_close,
            "r": r,
            "exit_reason": "TIME",
        }
