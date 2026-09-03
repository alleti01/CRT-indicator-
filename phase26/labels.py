"""Forward path labels for Phase 26 entry discovery."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from .config import HORIZON_BARS, PRIMARY_HORIZON_BARS, PRIMARY_LOSS_ATR, PRIMARY_PROFIT_ATR, SECONDARY_TARGETS


def _eval_path(
    i: int,
    horizon: int,
    direction: int,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    atr: float,
    profit_atr: float,
    loss_atr: float,
) -> Tuple[bool, float, float, int, int, float]:
    entry = close[i]
    if direction == 1:
        profit = entry + profit_atr * atr
        stop = entry - loss_atr * atr
    else:
        profit = entry - profit_atr * atr
        stop = entry + loss_atr * atr

    mfe = mae = 0.0
    btmf = btma = -1
    for step, j in enumerate(range(i + 1, i + 1 + horizon), start=0):
        hi, lo = high[j], low[j]
        if direction == 1:
            bar_mfe = (hi - entry) / atr
            bar_mae = (entry - lo) / atr
            hit_profit = hi >= profit
            hit_stop = lo <= stop
        else:
            bar_mfe = (entry - lo) / atr
            bar_mae = (hi - entry) / atr
            hit_profit = lo <= profit
            hit_stop = hi >= stop
        if bar_mfe > mfe:
            mfe, btmf = bar_mfe, step
        if bar_mae > mae:
            mae, btma = bar_mae, step
        if hit_stop and not hit_profit:
            return False, mfe, mae, btmf, btma, -loss_atr
        if hit_profit and not hit_stop:
            return True, mfe, mae, btmf, btma, profit_atr
        if hit_profit and hit_stop:
            return False, mfe, mae, btmf, btma, -loss_atr
    final = (close[i + horizon] - entry) / atr * direction
    return False, mfe, mae, btmf, btma, final


def build_path_labels(market: pd.DataFrame) -> pd.DataFrame:
    close = market["close"].to_numpy(dtype=float)
    high = market["high"].to_numpy(dtype=float)
    low = market["low"].to_numpy(dtype=float)
    atr = market["atr"].to_numpy(dtype=float)
    n = len(market)
    max_h = max(max(HORIZON_BARS), PRIMARY_HORIZON_BARS)

    columns = {}
    for side, direction in (("long", 1), ("short", -1)):
        primary = np.zeros(n, dtype=bool)
        mfe = np.full(n, np.nan)
        mae = np.full(n, np.nan)
        ratio = np.full(n, np.nan)
        t_mfe = np.full(n, np.nan)
        t_mae = np.full(n, np.nan)
        net_atr = np.full(n, np.nan)
        for h in HORIZON_BARS:
            columns[f"{side}_hit_{h}bar"] = np.zeros(n, dtype=bool)
        for pa, la in SECONDARY_TARGETS:
            columns[f"{side}_p{pa}_before_l{la}"] = np.zeros(n, dtype=bool)

        for i in range(n - max_h):
            a = atr[i]
            if not np.isfinite(a) or a <= 0:
                continue
            hit, mf, ma, btmf, btma, net = _eval_path(
                i, PRIMARY_HORIZON_BARS, direction, close, high, low, a, PRIMARY_PROFIT_ATR, PRIMARY_LOSS_ATR
            )
            primary[i] = hit
            mfe[i], mae[i], t_mfe[i], t_mae[i], net_atr[i] = mf, ma, float(btmf), float(btma), net
            if ma > 0:
                ratio[i] = mf / ma
            for h in HORIZON_BARS:
                h_hit, *_ = _eval_path(i, h, direction, close, high, low, a, PRIMARY_PROFIT_ATR, PRIMARY_LOSS_ATR)
                columns[f"{side}_hit_{h}bar"][i] = h_hit
            for pa, la in SECONDARY_TARGETS:
                s_hit, *_ = _eval_path(i, PRIMARY_HORIZON_BARS, direction, close, high, low, a, pa, la)
                columns[f"{side}_p{pa}_before_l{la}"][i] = s_hit

        columns[f"{side}_primary_hit"] = primary
        columns[f"{side}_mfe_atr"] = mfe
        columns[f"{side}_mae_atr"] = mae
        columns[f"{side}_mfe_mae_ratio"] = ratio
        columns[f"{side}_bars_to_mfe"] = t_mfe
        columns[f"{side}_bars_to_mae"] = t_mae
        columns[f"{side}_net_atr"] = net_atr

    labels = pd.DataFrame(columns, index=market.index)
    labels["eligible"] = np.isfinite(atr) & (np.arange(n) < (n - max_h))
    return labels
