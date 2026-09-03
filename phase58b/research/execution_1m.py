"""1M execution engine — price improvement after 5M TAKE."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58b.research.precompute import MTFArrays


def execute_1m(
    m: MTFArrays,
    take: dict,
    cfg: dict,
    variant: str = "X1",
) -> dict:
    """Resolve 1M entry for a 5M TAKE signal. Variants X0/X1/X2."""
    d = take["direction"]
    start_i = int(take["exec_m1_i"])
    decision_price = take["take_price"]
    max_delay = cfg.get("max_exec_delay_bars_1m", 2)
    max_chase = cfg.get("max_chase_atr", 1.5)

    if start_i >= m.m1_n - cfg.get("max_hold_min", 60) - 1:
        return _missed(take, variant, "OOB", start_i, decision_price)

    a = _atr(m.m1_atr[start_i], m.m1_atr, start_i)

    if variant == "X0":
        entry_i = start_i
        entry_price = m.m1_op[entry_i] if entry_i < m.m1_n else m.m1_cl[entry_i - 1]
        return _fill(take, variant, entry_i, entry_price, decision_price, a, "X0_IMMEDIATE")

    window_end = min(m.m1_n - 1, start_i + (1 if variant == "X1" else max_delay))
    best_i = -1
    best_price = np.nan

    for i in range(start_i, window_end + 1):
        det = (m.m1_cl[i] - decision_price) / a if d == "LONG" else (decision_price - m.m1_cl[i]) / a
        if det > max_chase:
            continue
        if _favorable_bar(m, i, d, cfg):
            ep = m.m1_cl[i]
            if d == "LONG":
                if not np.isfinite(best_price) or ep < best_price:
                    best_price = ep
                    best_i = i
            else:
                if not np.isfinite(best_price) or ep > best_price:
                    best_price = ep
                    best_i = i

    if best_i >= 0:
        return _fill(take, variant, best_i + 1, m.m1_op[min(best_i + 1, m.m1_n - 1)], decision_price, a, f"{variant}_FAVORABLE")

    # Fallback: X0 at window end if no favorable bar
    entry_i = start_i
    det = (m.m1_cl[entry_i] - decision_price) / a if d == "LONG" else (decision_price - m.m1_cl[entry_i]) / a
    if det > max_chase:
        return _missed(take, variant, "MISSED_NO_CHASE", entry_i, decision_price, det)
    entry_price = m.m1_op[entry_i]
    return _fill(take, variant, entry_i, entry_price, decision_price, a, f"{variant}_FALLBACK")


def execute_all_variants(m: MTFArrays, takes: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    rows = []
    for _, t in takes.iterrows():
        take = t.to_dict()
        for variant in ("X0", "X1", "X2"):
            rows.append(execute_1m(m, take, cfg, variant))
        # E5 baseline: next 5M open
        j = int(take["take_j"])
        e5_i = int(m.m5_close_m1_i[j])
        e5_price = m.m1_op[e5_i] if e5_i < m.m1_n else np.nan
        a = _atr(m.m1_atr[e5_i], m.m1_atr, e5_i)
        rows.append({
            **{k: take.get(k) for k in ("setup_id", "direction", "take_j", "take_price", "take_ts", "tag")},
            "variant": "E5",
            "entry_i": e5_i,
            "entry_price": e5_price,
            "entry_ts": str(m.m1_idx[e5_i]) if e5_i < m.m1_n else "",
            "exec_state": "E5_NEXT_5M_OPEN",
            "delay_bars_1m": e5_i - int(take["exec_m1_i"]),
            "price_improvement_atr": _improvement(take["direction"], take["take_price"], e5_price, a),
            "entry_deterioration_atr": _deterioration(take["direction"], take["take_price"], e5_price, a),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _favorable_bar(m: MTFArrays, i: int, direction: str, cfg: dict) -> bool:
    a = _atr(m.m1_atr[i], m.m1_atr, i)
    body = m.m1_cl[i] - m.m1_op[i]
    thresh = cfg.get("body_threshold_atr", 0.3) * 0.5
    if direction == "LONG":
        return body > 0 and body / a >= thresh
    return body < 0 and abs(body) / a >= thresh


def _fill(take, variant, entry_i, entry_price, decision_price, a, state) -> dict:
    return {
        "setup_id": take["setup_id"],
        "direction": take["direction"],
        "take_j": take["take_j"],
        "take_price": take["take_price"],
        "take_ts": take.get("take_ts", ""),
        "tag": take.get("tag", "CONTINUATION"),
        "variant": variant,
        "entry_i": entry_i,
        "entry_price": entry_price,
        "entry_ts": "",
        "exec_state": state,
        "delay_bars_1m": entry_i - int(take.get("exec_m1_i", entry_i)),
        "price_improvement_atr": _improvement(take["direction"], decision_price, entry_price, a),
        "entry_deterioration_atr": _deterioration(take["direction"], decision_price, entry_price, a),
    }


def _missed(take, variant, state, entry_i, decision_price, det=0) -> dict:
    return {
        "setup_id": take["setup_id"],
        "direction": take["direction"],
        "take_j": take["take_j"],
        "take_price": take["take_price"],
        "take_ts": take.get("take_ts", ""),
        "tag": take.get("tag", "CONTINUATION"),
        "variant": variant,
        "entry_i": -1,
        "entry_price": np.nan,
        "entry_ts": "",
        "exec_state": state,
        "delay_bars_1m": -1,
        "price_improvement_atr": 0.0,
        "entry_deterioration_atr": det,
    }


def _improvement(direction, decision, entry, a) -> float:
    if not np.isfinite(entry) or a <= 0:
        return 0.0
    if direction == "LONG":
        return max(0, (decision - entry) / a)
    return max(0, (entry - decision) / a)


def _deterioration(direction, decision, entry, a) -> float:
    if not np.isfinite(entry) or a <= 0:
        return 0.0
    if direction == "LONG":
        return max(0, (entry - decision) / a)
    return max(0, (decision - entry) / a)


def _atr(val: float, arr: np.ndarray, i: int) -> float:
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, i - 5), i + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0
