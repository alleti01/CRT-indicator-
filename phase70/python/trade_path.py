"""Phase70 — bar-by-bar trade path for execution intelligence."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


R_LEVELS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5]
ADV_LEVELS = [0.25, 0.5, 0.75, 1.0]


@dataclass
class TradePath:
    trade_id: str
    direction: str
    entry_i: int
    entry_price: float
    atr: float
    risk: float
    stop_price: float
    target_price: float
    m0_gross_r: float = 0.0
    m0_exit_bar: int = -1
    m0_exit_reason: str = ""
    m0_winner: bool = False
    time_to_fav: dict = field(default_factory=dict)
    time_to_adv: dict = field(default_factory=dict)
    bars: list = field(default_factory=list)


def walk_trade_path(
    trade_id: str,
    direction: str,
    ei: int,
    ep: float,
    atr: float,
    hi, lo, cl, op,
    stop_atr: float = 1.0,
    target_r: float = 2.5,
    max_hold: int = 60,
) -> TradePath:
    d = 1 if direction == "LONG" else -1
    risk = stop_atr * atr
    if risk <= 0:
        risk = max(0.25 * atr, 1e-9)
    stop = ep - d * risk
    target = ep + d * target_r * risk
    n = len(hi)
    end = min(ei + max_hold, n - 1)

    tp = TradePath(trade_id, direction, ei, ep, atr, risk, stop, target)
    ttf = {r: None for r in R_LEVELS}
    tta = {a: None for a in ADV_LEVELS}
    peak_r = mfe = mae = 0.0
    bars = []

    for k in range(ei + 1, end + 1):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        fav = (h - ep) * d / risk
        adv = (ep - l) / risk if d == 1 else (h - ep) / risk
        fav_c = (c - ep) * d / risk
        mfe = max(mfe, fav)
        mae = max(mae, adv)
        peak_r = max(peak_r, fav)

        for r in R_LEVELS:
            if ttf[r] is None and fav >= r:
                ttf[r] = k - ei
        for a in ADV_LEVELS:
            if tta[a] is None and adv >= a:
                tta[a] = k - ei

        hit_stop = l <= stop if d == 1 else h >= stop
        hit_tgt = h >= target if d == 1 else l <= target

        bars.append({
            "bar_i": k, "minutes": k - ei, "high": h, "low": l, "close": c,
            "open": float(op[k]), "fav_r": fav, "adv_r": adv, "close_r": fav_c,
            "mfe_r": mfe, "mae_r": mae, "peak_r": peak_r,
            "hit_stop": hit_stop, "hit_tgt": hit_tgt,
        })

        if hit_stop and hit_tgt:
            tp.m0_gross_r = -1.0
            tp.m0_exit_bar = k
            tp.m0_exit_reason = "INITIAL_STOP"
            break
        if hit_stop:
            tp.m0_gross_r = -1.0
            tp.m0_exit_bar = k
            tp.m0_exit_reason = "INITIAL_STOP"
            break
        if hit_tgt:
            tp.m0_gross_r = target_r
            tp.m0_exit_bar = k
            tp.m0_exit_reason = "FIXED_TARGET"
            break
        if k == end:
            tp.m0_gross_r = fav_c
            tp.m0_exit_bar = k
            tp.m0_exit_reason = "MAX_HOLD"
    else:
        pass

    tp.time_to_fav = ttf
    tp.time_to_adv = tta
    tp.bars = bars
    tp.m0_winner = tp.m0_gross_r > 0
    return tp


def simulate_managed_exit(
    path: TradePath,
    hi, lo, cl, op,
    rule: str,
    params: dict,
    cost_mult: float = 1.0,
) -> dict:
    """Apply one execution rule on precomputed path. Returns trade result."""
    from phase58.research.instrument import NQ

    d = 1 if path.direction == "LONG" else -1
    ep, risk = path.entry_price, path.risk
    extra_cost = 0.0

    for bar in path.bars:
        k = bar["bar_i"]
        mins = bar["minutes"]
        h, l, c = bar["high"], bar["low"], bar["close"]

        if rule == "NO_PROGRESS":
            checkpoint = params["minutes"]
            mfe_thresh = params["mfe_r"]
            if mins >= checkpoint and bar["mfe_r"] < mfe_thresh:
                exit_r = bar["close_r"]
                reason = f"NO_PROGRESS_{checkpoint}M"
                return _result(path, k, exit_r, reason, path.m0_gross_r, cost_mult, extra_cost)

        elif rule == "HARD_TIMEOUT":
            if mins >= params["minutes"]:
                exit_r = bar["close_r"]
                return _result(path, k, exit_r, f"TIME_LIMIT_{params['minutes']}M", path.m0_gross_r, cost_mult, extra_cost)

        elif rule == "FAILURE":
            window = params.get("window", 5)
            if mins <= window:
                opp_disp = (float(op[k]) - c) * d / path.atr if d == 1 else (c - float(op[k])) * d / path.atr
                if bar["mae_r"] >= params.get("mae_r", 0.75) and bar["mfe_r"] < params.get("mfe_r", 0.25):
                    exit_r = bar["close_r"]
                    return _result(path, k, exit_r, "STRUCTURE_FAILURE", path.m0_gross_r, cost_mult, extra_cost)
                if opp_disp >= params.get("opp_atr", 1.0):
                    # structure break: 5-bar causal low/high
                    i0 = max(path.entry_i, k - 4)
                    if d == 1 and l < float(np.min(lo[i0:k])):
                        exit_r = bar["close_r"]
                        return _result(path, k, exit_r, "OPPOSITE_DISPLACEMENT", path.m0_gross_r, cost_mult, extra_cost)
                    if d == -1 and h > float(np.max(hi[i0:k])):
                        exit_r = bar["close_r"]
                        return _result(path, k, exit_r, "OPPOSITE_DISPLACEMENT", path.m0_gross_r, cost_mult, extra_cost)

        # M0 stop/target (STOP_FIRST)
        if bar["hit_stop"] and bar["hit_tgt"]:
            return _result(path, k, -1.0, "HARD_STOP", path.m0_gross_r, cost_mult, 0)
        if bar["hit_stop"]:
            return _result(path, k, -1.0, "HARD_STOP", path.m0_gross_r, cost_mult, 0)
        if bar["hit_tgt"]:
            return _result(path, k, 2.5, "M0_TARGET", path.m0_gross_r, cost_mult, 0)

    last = path.bars[-1] if path.bars else None
    if last:
        return _result(path, last["bar_i"], last["close_r"], "MAX_HOLD", path.m0_gross_r, cost_mult, 0)
    return _result(path, path.entry_i, 0.0, "NO_DATA", path.m0_gross_r, cost_mult, 0)


def _result(path, exit_i, gross_r, reason, m0_gross, cost_mult, extra_cost):
    from phase58.research.instrument import NQ
    base_cost = NQ.cost_r(path.entry_price, path.risk) * cost_mult
    ec = base_cost * (1.0 + extra_cost)
    m0_net = m0_gross - base_cost
    net = gross_r - ec
    killed = path.m0_gross_r >= 2.5 - 1e-9 and gross_r < 2.5 - 0.01
    saved_stop = path.m0_gross_r <= -0.99 and gross_r > -0.99
    return {
        "trade_id": path.trade_id,
        "direction": path.direction,
        "entry_i": path.entry_i,
        "exit_i": exit_i,
        "gross_R": gross_r,
        "net_R": net,
        "cost_R": ec,
        "exit_reason": reason,
        "m0_gross_R": m0_gross,
        "m0_net_R": m0_net,
        "incremental_net_R": net - m0_net,
        "killed_winner": killed,
        "saved_stop": saved_stop,
        "duration": exit_i - path.entry_i,
    }


def classify_time_exit(m0_gross: float, exit_gross: float) -> str:
    if m0_gross <= -0.99:
        return "SAVED_STOP" if exit_gross > -0.99 else "NO_DIFFERENCE"
    if m0_gross >= 2.5 - 1e-9:
        return "KILLED_LATER_WINNER" if exit_gross < 2.5 - 0.01 else "NO_DIFFERENCE"
    if exit_gross > m0_gross + 0.05:
        return "CUT_SMALL_LOSS" if m0_gross < 0 else "CUT_SMALL_WIN"
    if abs(exit_gross) < 0.1 and abs(m0_gross) < 0.1:
        return "CUT_BREAKEVEN"
    return "NO_DIFFERENCE"
