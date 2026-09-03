"""Phase72 — clean-room independent simulator (no canonical_trader imports)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ

FREEZE_PATH = Path(__file__).resolve().parents[1] / "freeze" / "PHASE71_FORWARD_FREEZE.json"
if not FREEZE_PATH.exists():
    FREEZE_PATH = Path(__file__).resolve().parents[2] / "phase71" / "freeze" / "PHASE71_FORWARD_FREEZE.json"

SPEC = json.loads(FREEZE_PATH.read_text())


def _load_spec() -> dict:
    return SPEC


def simulate_trade(
    direction: str,
    entry_i: int,
    entry_price: float,
    initial_atr: float,
    hi, lo, cl, op,
    n: int,
    enable_t5: bool = True,
) -> dict:
    """Independent implementation of frozen Phase71 management rules."""
    spec = _load_spec()
    stop_atr = float(spec["initial_stop_atr"])
    target_r = float(spec["target_r"])
    max_hold = int(spec["max_hold_minutes"])
    t5_min = int(spec["t5_minutes"])
    t5_thr = float(spec["t5_mfe_threshold_r"])

    d = 1 if direction == "LONG" else -1
    risk = stop_atr * initial_atr
    if risk <= 0:
        risk = max(0.25 * initial_atr, 1e-9)
    ep = float(entry_price)
    stop = ep - d * risk
    target = ep + d * target_r * risk
    end_i = min(entry_i + max_hold, n - 1)

    run_mfe = 0.0
    t5_checked = False
    t5_time = None
    mfe_at_t5 = None
    t5_result = None

    for k in range(entry_i + 1, end_i + 1):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        minutes = k - entry_i

        hs = l <= stop if d == 1 else h >= stop
        ht = h >= target if d == 1 else l <= target

        if hs and ht:
            return _pack(ep, risk, d, k, -1.0, stop, "M0_STOP", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)
        if hs:
            return _pack(ep, risk, d, k, -1.0, stop, "M0_STOP", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)
        if ht:
            return _pack(ep, risk, d, k, target_r, target, "M0_TARGET", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)

        fav = (h - ep) * d / risk
        run_mfe = max(run_mfe, fav)

        if enable_t5 and not t5_checked and minutes >= t5_min:
            t5_checked = True
            t5_time = k
            mfe_at_t5 = run_mfe
            if run_mfe < t5_thr:
                t5_result = "FAIL"
                gr = (c - ep) * d / risk
                return _pack(ep, risk, d, k, gr, c, "T5_NO_PROGRESS", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)
            t5_result = "PASS"

        if k == end_i:
            gr = (c - ep) * d / risk
            return _pack(ep, risk, d, k, gr, c, "MAX_HOLD_60M", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)

    return _pack(ep, risk, d, entry_i, 0.0, ep, "NO_EXIT", 0, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)


def continue_trade_from(
    direction: str,
    entry_i: int,
    entry_price: float,
    initial_atr: float,
    stop: float,
    target: float,
    risk: float,
    resume_i: int,
    running_mfe: float,
    t5_checked: bool,
    hi, lo, cl, op,
    n: int,
    enable_t5: bool = True,
) -> dict:
    """Resume management from bar resume_i (state known after that bar closed)."""
    spec = _load_spec()
    stop_atr = float(spec["initial_stop_atr"])
    target_r = float(spec["target_r"])
    max_hold = int(spec["max_hold_minutes"])
    t5_min = int(spec["t5_minutes"])
    t5_thr = float(spec["t5_mfe_threshold_r"])
    d = 1 if direction == "LONG" else -1
    ep = float(entry_price)
    end_i = min(entry_i + max_hold, n - 1)
    run_mfe = running_mfe
    t5_checked = t5_checked
    t5_time = None
    mfe_at_t5 = None
    t5_result = None

    for k in range(resume_i + 1, end_i + 1):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        minutes = k - entry_i
        hs = l <= stop if d == 1 else h >= stop
        ht = h >= target if d == 1 else l <= target
        if hs and ht:
            return _pack(ep, risk, d, k, -1.0, stop, "M0_STOP", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)
        if hs:
            return _pack(ep, risk, d, k, -1.0, stop, "M0_STOP", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)
        if ht:
            return _pack(ep, risk, d, k, target_r, target, "M0_TARGET", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)
        fav = (h - ep) * d / risk
        run_mfe = max(run_mfe, fav)
        if enable_t5 and not t5_checked and minutes >= t5_min:
            t5_checked = True
            t5_time = k
            mfe_at_t5 = run_mfe
            if run_mfe < t5_thr:
                t5_result = "FAIL"
                gr = (c - ep) * d / risk
                return _pack(ep, risk, d, k, gr, c, "T5_NO_PROGRESS", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)
            t5_result = "PASS"
        if k == end_i:
            gr = (c - ep) * d / risk
            return _pack(ep, risk, d, k, gr, c, "MAX_HOLD_60M", minutes, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)
    return _pack(ep, risk, d, entry_i, 0.0, ep, "NO_EXIT", 0, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr)


def _pack(ep, risk, d, exit_i, gross_r, exit_px, reason, hold, t5_time, mfe_at_t5, t5_result, entry_i, initial_atr):
    cost = NQ.cost_r(ep, risk)
    return {
        "entry_i": entry_i,
        "exit_i": exit_i,
        "entry_price": ep,
        "exit_price": exit_px,
        "gross_r": gross_r,
        "net_r": gross_r - cost,
        "exit_reason": reason,
        "hold_minutes": hold,
        "t5_time": t5_time,
        "mfe_at_t5_r": mfe_at_t5,
        "t5_result": t5_result,
        "stop_price": ep - d * risk,
        "target_price": ep + d * 2.5 * risk,
        "initial_atr": initial_atr,
    }


def run_one_position_independent(execs: pd.DataFrame, m, enable_t5: bool = True) -> tuple[pd.DataFrame, dict]:
    execs = execs.sort_values("entry_ts").reset_index(drop=True)
    trades = []
    skipped = {"N": 0, "LONG": 0, "SHORT": 0}
    active_until = -1
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65 or ei <= active_until:
            skipped["N"] += 1
            skipped[ex["direction"]] = skipped.get(ex["direction"], 0) + 1
            continue
        atr = float(ex["atr_entry"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        rec = simulate_trade(ex["direction"], ei, float(ex["entry_price"]), atr,
                             m.hi, m.lo, m.cl, m.op, m.n, enable_t5)
        rec["trade_id"] = ex["trade_id"]
        rec["direction"] = ex["direction"]
        trades.append(rec)
        active_until = rec["exit_i"]
    return pd.DataFrame(trades), skipped


def run_independent_batch(execs: pd.DataFrame, m, enable_t5: bool = True) -> pd.DataFrame:
    rows = []
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        atr = float(ex["atr_entry"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        rec = simulate_trade(ex["direction"], ei, float(ex["entry_price"]), atr,
                             m.hi, m.lo, m.cl, m.op, m.n, enable_t5)
        rec["trade_id"] = ex["trade_id"]
        rec["direction"] = ex["direction"]
        rows.append(rec)
    return pd.DataFrame(rows)
