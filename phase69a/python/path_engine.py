"""Phase69A — unified bar-by-bar path engine (M0 + MFE + runner analysis)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


FIRST_PASSAGE_TESTS = [
    ("3_before_2", 3.0, 2.0), ("4_before_2", 4.0, 2.0), ("5_before_2", 5.0, 2.0), ("7_before_2", 7.0, 2.0),
    ("3_before_1.5", 3.0, 1.5), ("4_before_1.5", 4.0, 1.5), ("5_before_1.5", 5.0, 1.5), ("7_before_1.5", 7.0, 1.5),
    ("4_before_1", 4.0, 1.0), ("5_before_1", 5.0, 1.0), ("7_before_1", 7.0, 1.0),
    ("5_before_0", 5.0, 0.0), ("7_before_0", 7.0, 0.0),
]

CONTINUATION_LEVELS = [3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0]
CONTINUATION_WINDOWS = [5, 10, 15, 30, 60, 90, 120]
GIVEBACK_LEVELS = [3.0, 4.0, 5.0, 7.0, 10.0]
REVERSAL_LEVELS = [2.0, 1.5, 1.0, 0.5, 0.0, -1.0]
REVERSAL_TARGETS = [3.0, 4.0, 5.0, 7.0]


@dataclass
class PathResult:
    trade_id: str
    direction: str
    entry_i: int
    entry_ts: object = None
    entry_price: float = 0.0
    atr: float = 0.0
    stop_price: float = 0.0
    target_price: float = 0.0
    risk: float = 0.0
    first_touch_class: str = "DATA_END_BEFORE_EITHER"
    first_stop_bar: Optional[int] = None
    first_target_bar: Optional[int] = None
    same_bar_collision: bool = False
    m0_exit_bar: int = -1
    m0_exit_reason: str = ""
    m0_gross_r: float = 0.0
    mfe_a: float = 0.0
    mfe_b: float = 0.0
    mfe_c: float = 0.0
    mae_a: float = 0.0
    mae_b: float = 0.0
    mae_c: float = 0.0
    first_2p5_bar_unconditional: Optional[int] = None
    true_2p5_winner: bool = False
    t_2p5_bar: Optional[int] = None
    later_2p5_after_stop: bool = False
    post_2p5_peak_r: float = 0.0
    first_passage: dict = field(default_factory=dict)
    continuation: dict = field(default_factory=dict)
    giveback: dict = field(default_factory=dict)
    reversal: dict = field(default_factory=dict)
    immediate: dict = field(default_factory=dict)
    time_to_ext: dict = field(default_factory=dict)
    option_b_r: Optional[float] = None
    bar_trace: list = field(default_factory=list, repr=False)


def _fav_adv(h: float, l: float, ep: float, risk: float, d: int) -> tuple[float, float]:
    if d == 1:
        return (h - ep) / risk, (ep - l) / risk
    return (ep - l) / risk, (h - ep) / risk


def _level_price(ep: float, risk: float, r_level: float, d: int) -> float:
    return ep + d * r_level * risk


def _first_bar_touch(hi, lo, k0: int, k1: int, ep: float, risk: float, d: int, r_level: float, side: str) -> Optional[int]:
    """side='high' for favorable touch, 'low' for adverse retrace to profit level."""
    px = _level_price(ep, risk, r_level, d)
    for k in range(k0, k1 + 1):
        h, l = float(hi[k]), float(lo[k])
        if side == "high":
            if d == 1 and h >= px:
                return k
            if d == -1 and l <= px:
                return k
        else:
            if d == 1 and l <= px:
                return k
            if d == -1 and h >= px:
                return k
    return None


def walk_path(
    trade_id: str,
    direction: str,
    ei: int,
    ep: float,
    atr: float,
    hi, lo, cl, op,
    stop_atr: float = 1.0,
    target_r: float = 2.5,
    max_hold: int = 60,
    horizon: int = 120,
    entry_ts=None,
    capture_trace: bool = False,
) -> PathResult:
    d = 1 if direction == "LONG" else -1
    risk = stop_atr * atr
    if risk <= 0:
        risk = max(0.25 * atr, 1e-9)
    stop = ep - d * risk
    target = ep + d * target_r * risk
    n = len(hi)
    end_m0 = min(ei + max_hold, n - 1)
    end_h = min(ei + horizon, n - 1)

    res = PathResult(
        trade_id=trade_id, direction=direction, entry_i=ei, entry_ts=entry_ts,
        entry_price=ep, atr=atr, stop_price=stop, target_price=target, risk=risk,
    )

    first_stop: Optional[int] = None
    first_tgt: Optional[int] = None
    first_2p5_any: Optional[int] = None
    m0_done = False
    stop_alive = True

    trace = []

    for k in range(ei + 1, end_h + 1):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        fav, adv = _fav_adv(h, l, ep, risk, d)

        res.mfe_a = max(res.mfe_a, fav)
        res.mae_a = max(res.mae_a, adv)
        if fav >= target_r and first_2p5_any is None:
            first_2p5_any = k
        if stop_alive:
            res.mfe_c = max(res.mfe_c, fav)
            res.mae_c = max(res.mae_c, adv)

        hit_stop = l <= stop if d == 1 else h >= stop
        hit_tgt = h >= target if d == 1 else l <= target

        if not m0_done and k <= end_m0:
            res.mfe_b = max(res.mfe_b, fav)
            res.mae_b = max(res.mae_b, adv)
            if first_stop is None and hit_stop:
                first_stop = k
            if first_tgt is None and hit_tgt:
                first_tgt = k
            if hit_stop and hit_tgt:
                m0_done = True
                res.m0_exit_bar = k
                res.m0_exit_reason = "INITIAL_STOP"
                res.m0_gross_r = -1.0
                res.same_bar_collision = True
            elif hit_stop:
                m0_done = True
                res.m0_exit_bar = k
                res.m0_exit_reason = "INITIAL_STOP"
                res.m0_gross_r = -1.0
            elif hit_tgt:
                m0_done = True
                res.m0_exit_bar = k
                res.m0_exit_reason = "FIXED_TARGET"
                res.m0_gross_r = target_r
            elif k == end_m0:
                m0_done = True
                res.m0_exit_bar = k
                res.m0_exit_reason = "MAX_HOLD"
                res.m0_gross_r = (c - ep) * d / risk

        if stop_alive and hit_stop:
            stop_alive = False

        if capture_trace:
            trace.append({
                "bar_i": k, "open": float(op[k]), "high": h, "low": l, "close": c,
                "fav_r": fav, "adv_r": adv, "mfe_a": res.mfe_a, "mae_a": res.mae_a,
            })

    if first_stop is not None and first_tgt is not None and first_stop == first_tgt:
        res.first_touch_class = "SAME_BAR_STOP_AND_2P5"
    elif first_tgt is not None and (first_stop is None or first_tgt < first_stop):
        res.first_touch_class = "TARGET_2P5_BEFORE_STOP"
    elif first_stop is not None and (first_tgt is None or first_stop < first_tgt):
        res.first_touch_class = "STOP_BEFORE_2P5"
    elif res.m0_exit_reason == "MAX_HOLD":
        res.first_touch_class = "TIMEOUT_BEFORE_EITHER"
    else:
        res.first_touch_class = "DATA_END_BEFORE_EITHER"

    res.first_stop_bar = first_stop
    res.first_target_bar = first_tgt
    res.first_2p5_bar_unconditional = first_2p5_any
    res.true_2p5_winner = res.first_touch_class == "TARGET_2P5_BEFORE_STOP"
    res.t_2p5_bar = first_tgt if res.true_2p5_winner else None
    res.later_2p5_after_stop = (
        first_stop is not None and first_2p5_any is not None and first_stop < first_2p5_any
    )

    if res.true_2p5_winner and res.t_2p5_bar is not None:
        _analyze_post_2p5(res, hi, lo, cl, op, ep, risk, d, end_h, capture_trace, trace)

    if capture_trace:
        res.bar_trace = trace
    return res


def _analyze_post_2p5(res, hi, lo, cl, op, ep, risk, d, end_h, capture_trace, trace):
    t0 = res.t_2p5_bar
    peak_r = 2.5
    res.post_2p5_peak_r = 2.5

    for name, pos, neg in FIRST_PASSAGE_TESTS:
        tp = _first_bar_touch(hi, lo, t0, end_h, ep, risk, d, pos, "high")
        tn = _first_bar_touch(hi, lo, t0, end_h, ep, risk, d, neg, "low")
        if tp is None and tn is None:
            res.first_passage[name] = None
        elif tp is None:
            res.first_passage[name] = False
        elif tn is None:
            res.first_passage[name] = True
        else:
            res.first_passage[name] = tp <= tn

    for mins in CONTINUATION_WINDOWS:
        k1 = min(t0 + mins, end_h)
        peak = 2.5
        for k in range(t0, k1 + 1):
            fav, _ = _fav_adv(float(hi[k]), float(lo[k]), ep, risk, d)
            peak = max(peak, fav)
        for lvl in CONTINUATION_LEVELS:
            lbl = f"{lvl:g}R_within_{mins}m"
            res.continuation[lbl] = peak >= lvl

    for lvl in GIVEBACK_LEVELS:
        peak = 2.5
        max_dd = 0.0
        reached = False
        for k in range(t0, end_h + 1):
            fav, _ = _fav_adv(float(hi[k]), float(lo[k]), ep, risk, d)
            peak = max(peak, fav)
            dd = peak - fav
            max_dd = max(max_dd, dd)
            if fav >= lvl:
                reached = True
                break
        res.giveback[f"to_{lvl}R"] = max_dd if reached else None

    for tgt in REVERSAL_TARGETS:
        t_hit = _first_bar_touch(hi, lo, t0, end_h, ep, risk, d, tgt, "high")
        for rev in REVERSAL_LEVELS:
            key = f"retrace_{rev:g}R_before_{tgt:g}R"
            r_hit = _first_bar_touch(hi, lo, t0, end_h, ep, risk, d, rev, "low")
            if t_hit is None:
                res.reversal[key] = None
            elif r_hit is None:
                res.reversal[key] = False
            else:
                res.reversal[key] = r_hit < t_hit

    c0 = float(cl[t0])
    res.immediate["ret_1m"] = (float(cl[min(t0 + 1, end_h)]) - c0) * d / risk if t0 + 1 <= end_h else None
    for m in [2, 3, 5, 10]:
        k = min(t0 + m, end_h)
        res.immediate[f"ret_{m}m"] = (float(cl[k]) - c0) * d / risk if k > t0 else None
    for m in [1, 2, 3, 5]:
        k1 = min(t0 + m, end_h)
        peak = 2.5
        for k in range(t0, k1 + 1):
            fav, _ = _fav_adv(float(hi[k]), float(lo[k]), ep, risk, d)
            peak = max(peak, fav)
        res.immediate[f"new_extreme_{m}m"] = peak > 2.5 + 1e-9

    for lvl in [3.0, 4.0, 5.0, 7.0, 10.0]:
        tb = _first_bar_touch(hi, lo, t0, end_h, ep, risk, d, lvl, "high")
        res.time_to_ext[f"2p5_to_{lvl:g}R_min"] = (tb - t0) if tb is not None else None

    # Option B: no target, original stop only to horizon
    exit_r = 2.5
    exited = False
    for k in range(t0 + 1, end_h + 1):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        if d == 1 and l <= res.stop_price:
            exit_r = -1.0
            exited = True
            break
        if d == -1 and h >= res.stop_price:
            exit_r = -1.0
            exited = True
            break
    if not exited:
        exit_r = (float(cl[end_h]) - ep) * d / risk
        peak = 2.5
        for k in range(t0, end_h + 1):
            fav, _ = _fav_adv(float(hi[k]), float(lo[k]), ep, risk, d)
            peak = max(peak, fav)
        res.post_2p5_peak_r = peak
    else:
        res.post_2p5_peak_r = max(
            2.5,
            max(_fav_adv(float(hi[k]), float(lo[k]), ep, risk, d)[0] for k in range(t0, end_h + 1)),
        )
    res.option_b_r = exit_r


def phase69_buggy_reached_2p5(ei: int, direction: str, ep: float, risk: float, hi, lo, n: int) -> bool:
    """Exact reproduction of phase69/python/path_audit.py counterfactual_after_r."""
    d = 1 if direction == "LONG" else -1
    end = min(ei + 121, n)
    hs, ls = hi[ei:end], lo[ei:end]
    if d == 1:
        fav = (np.maximum.accumulate(hs) - ep) / risk
    else:
        fav = (ep - np.minimum.accumulate(ls)) / risk
    return bool(np.any(fav >= 2.5))


def runner_partial_r(main_frac: float, runner_frac: float, main_r: float, runner_exit_r: float) -> float:
    return main_frac * main_r + runner_frac * runner_exit_r
