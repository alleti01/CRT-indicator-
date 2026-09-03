"""Phase69 — causal exit management simulation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase52.research.swings import precompute_last2_swing_lows, precompute_last2_swing_highs
from phase58.research.instrument import NQ


def _risk_stop(entry: float, direction: str, atr: float, stop_atr: float = 1.0) -> tuple[float, float]:
    risk = stop_atr * atr
    if direction == "LONG":
        return entry - risk, risk
    return entry + risk, risk


def walk_trade(hi, lo, cl, op, ei: int, direction: str, ep: float, atr: float,
               stop_atr: float = 1.0, target_r: float | None = 2.5, max_hold: int = 60,
               mode: str = "M0", params: dict | None = None, sh1=None, sl1=None) -> dict:
    """Simulate one trade from entry bar open."""
    params = params or {}
    d = 1 if direction == "LONG" else -1
    stop, risk = _risk_stop(ep, direction, atr, stop_atr)
    if risk <= 0:
        risk = 0.25 * atr
    initial_stop = stop
    target = ep + d * (target_r or 999) * risk if target_r is not None else None

    peak_r = 0.0
    mfe = mae = 0.0
    cur_stop = stop
    partial_r = 0.0
    partial_taken = False
    runner_frac = params.get("runner_frac", 1.0)
    activation = params.get("activation_r", 999.0)
    trail_atr = params.get("trail_atr", 1.5)
    giveback_r = params.get("giveback_r", 1.0)
    peak_price = ep
    last_extreme_i = ei
    n = len(hi)

    for k in range(ei + 1, min(ei + max_hold + 1, n)):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        if d == 1:
            peak_price = max(peak_price, h)
            fav = (peak_price - ep) / risk
            adv = (ep - l) / risk
            mfe = max(mfe, (h - ep) / risk)
            mae = max(mae, (ep - l) / risk)
        else:
            peak_price = min(peak_price, l)
            fav = (ep - peak_price) / risk
            adv = (h - ep) / risk
            mfe = max(mfe, (ep - l) / risk)
            mae = max(mae, (h - ep) / risk)
        peak_r = max(peak_r, fav)
        if fav > peak_r - 0.01:
            last_extreme_i = k

        # Partial at target
        if mode == "M5" and target_r is not None and not partial_taken and fav >= target_r:
            partial_frac = params.get("partial_frac", 0.5)
            partial_r = partial_frac * target_r
            partial_taken = True
            runner_frac = 1.0 - partial_frac
            if runner_frac <= 0:
                return _pack(ei, k, target_r, "PARTIAL_TARGET", mfe, mae, ep, risk, d, partial_r)

        # Activation-based trails
        if peak_r >= activation:
            if mode in ("M2", "M6") and trail_atr:
                if d == 1:
                    cur_stop = max(cur_stop, peak_price - trail_atr * atr)
                else:
                    cur_stop = min(cur_stop, peak_price + trail_atr * atr)
            if mode == "M3" and giveback_r:
                floor_r = peak_r - giveback_r
                if d == 1:
                    cur_stop = max(cur_stop, ep + floor_r * risk)
                else:
                    cur_stop = min(cur_stop, ep - floor_r * risk)
            if mode == "M1" and sh1 is not None and sl1 is not None:
                if d == 1 and np.isfinite(sl1[k]):
                    cur_stop = max(cur_stop, float(sl1[k]) - 0.05 * atr)
                elif d == -1 and np.isfinite(sh1[k]):
                    cur_stop = min(cur_stop, float(sh1[k]) + 0.05 * atr)
            if mode == "M4":
                for thr, prot in params.get("floors", [(2, 0.5), (3, 1.5), (4, 2.5), (5, 3.5)]):
                    if peak_r >= thr:
                        if d == 1:
                            cur_stop = max(cur_stop, ep + prot * risk)
                        else:
                            cur_stop = min(cur_stop, ep - prot * risk)
            if mode == "M6":
                # opposite displacement
                opp = params.get("opp_atr", 1.0)
                bar_disp = (c - op[k]) if d == 1 else (op[k] - c)
                if bar_disp <= -opp * atr:
                    exit_r = (c - ep) * d / risk
                    total = partial_r + runner_frac * exit_r
                    return _pack(ei, k, total, "OPPOSITE_DISPLACEMENT", mfe, mae, ep, risk, d, partial_r, runner_frac)
            if mode == "M6_STALL" and peak_r >= params.get("stall_min_r", 2.0):
                stall = params.get("stall_bars", 10)
                if k - last_extreme_i >= stall:
                    exit_r = (c - ep) * d / risk
                    total = partial_r + runner_frac * exit_r
                    return _pack(ei, k, total, "STALL", mfe, mae, ep, risk, d, partial_r, runner_frac)

        # Never widen stop
        if d == 1:
            cur_stop = max(cur_stop, initial_stop)
        else:
            cur_stop = min(cur_stop, initial_stop)

        hit_stop = l <= cur_stop if d == 1 else h >= cur_stop
        hit_tgt = (h >= target if d == 1 else l <= target) if target is not None and mode not in ("M2", "M3", "M1", "M4", "M6", "M6_STALL", "M5") else False
        if mode == "M5" and partial_taken and hit_stop:
            exit_r = (cur_stop - ep) * d / risk
            total = partial_r + runner_frac * exit_r
            reason = "RUNNER_STOP" if cur_stop != initial_stop else "INITIAL_STOP"
            return _pack(ei, k, total, reason, mfe, mae, ep, risk, d, partial_r, runner_frac)

        if hit_stop and hit_tgt:
            exit_r = -1.0
            total = partial_r + runner_frac * exit_r if partial_taken else exit_r
            return _pack(ei, k, total, "INITIAL_STOP", mfe, mae, ep, risk, d, partial_r, runner_frac)
        if hit_stop:
            exit_r = (cur_stop - ep) * d / risk
            reason = "INITIAL_STOP" if abs(cur_stop - initial_stop) < 0.01 else (
                "ATR_TRAIL" if mode == "M2" else "R_GIVEBACK" if mode == "M3" else
                "STRUCTURE_TRAIL" if mode == "M1" else "PROFIT_FLOOR" if mode == "M4" else "STOP")
            total = partial_r + runner_frac * exit_r if partial_taken else exit_r
            return _pack(ei, k, total, reason, mfe, mae, ep, risk, d, partial_r, runner_frac)
        if hit_tgt:
            total = target_r if not partial_taken else partial_r + runner_frac * target_r
            return _pack(ei, k, total, "FIXED_TARGET", mfe, mae, ep, risk, d, partial_r, runner_frac)

    c = float(cl[min(ei + max_hold, n - 1)])
    exit_r = (c - ep) * d / risk
    total = partial_r + runner_frac * exit_r if partial_taken else exit_r
    return _pack(ei, min(ei + max_hold, n - 1), total, "MAX_HOLD", mfe, mae, ep, risk, d, partial_r, runner_frac)


def _pack(ei, xi, gross_r, reason, mfe, mae, ep, risk, d, partial_r=0.0, runner_frac=1.0):
    cost = NQ.cost_r(ep, risk) * (1.0 + (0.5 if partial_r else 0.0))
    return {
        "exit_i": xi, "gross_R": gross_r, "cost_R": cost, "net_R": gross_r - cost,
        "exit_reason": reason, "MFE_R": mfe, "MAE_R": mae,
        "capture_eff": gross_r / mfe if mfe > 0 else 0,
        "duration": xi - ei,
    }


def simulate_batch(execs: pd.DataFrame, m, mode: str = "M0", target_r: float | None = 2.5,
                   max_hold: int = 60, params: dict | None = None) -> pd.DataFrame:
    params = params or {}
    sh1, _ = precompute_last2_swing_highs(m.hi, 5)
    sl1, _ = precompute_last2_swing_lows(m.lo, 5)
    rows = []
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        atr = float(ex["atr_entry"]) if ex["atr_entry"] > 0 else float(m.atr[ei])
        r = walk_trade(m.hi, m.lo, m.cl, m.op, ei, ex["direction"], float(ex["entry_price"]),
                       atr, stop_atr=1.0, target_r=target_r, max_hold=max_hold,
                       mode=mode, params=params, sh1=sh1, sl1=sl1)
        r["trade_id"] = ex["trade_id"]
        r["direction"] = ex["direction"]
        rows.append(r)
    return pd.DataFrame(rows)
