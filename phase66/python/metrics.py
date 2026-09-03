"""Phase66 — path metrics and simulation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ
from phase58b.research.simulation import metrics
from phase62.python.analysis import path_ordering


def path_from_entry(m, entry_i: int, direction: str, atr: float, max_h: int = 60) -> dict:
    ep = float(m.op[entry_i])
    a = atr if atr > 0 else 1.0
    end = min(entry_i + max_h, m.n)
    hs, ls = m.hi[entry_i:end], m.lo[entry_i:end]
    d = 1 if direction == "LONG" else -1
    if d == 1:
        fav = (np.maximum.accumulate(hs) - ep) / a
        adv = (ep - np.minimum.accumulate(ls)) / a
    else:
        fav = (ep - np.minimum.accumulate(ls)) / a
        adv = (np.maximum.accumulate(hs) - ep) / a
    po = path_ordering(m.hi, m.lo, m.op, entry_i, direction, a, max_h)
    mfe60 = float(np.max(fav)) if len(fav) else 0
    mae60 = float(np.max(adv)) if len(adv) else 0
    out = {"mfe_60m": mfe60, "mae_60m": mae60, "pairs": po["pairs"]}
    for h in [3, 5, 10, 15, 30]:
        sl = min(h, len(fav))
        out[f"mfe_{h}m"] = float(np.max(fav[:sl])) if sl else 0
        out[f"mae_{h}m"] = float(np.max(adv[:sl])) if sl else 0
    return out


def aggregate_paths(paths: list[dict]) -> dict:
    if not paths:
        return {"n": 0}
    pairs = {}
    totals = {}
    mfes = {k: [] for k in ["mfe_3m", "mfe_5m", "mfe_15m", "mfe_60m", "mae_3m", "mae_5m", "mae_15m", "mae_60m"]}
    for p in paths:
        for k in mfes:
            if k in p:
                mfes[k].append(p[k])
        for pname, val in p.get("pairs", {}).items():
            if val is None:
                continue
            totals[pname] = totals.get(pname, 0) + 1
            if val:
                pairs[pname] = pairs.get(pname, 0) + 1
    out = {k: pairs.get(k, 0) / totals[k] for k in totals}
    out["n"] = len(paths)
    for k, v in mfes.items():
        out[f"median_{k}"] = float(np.median(v)) if v else 0
    return out


def simulate_setup(m, sig, atr: float, target_r: float = 2.5, cost_mult: float = 1.0,
                   stop_mode: str = "setup") -> dict:
    """Setup-defined or fixed ATR stop."""
    ei = int(sig.entry_i)
    d = 1 if sig.direction == "LONG" else -1
    ep = float(m.op[ei])
    a = atr if atr > 0 else 1.0
    inv = float(sig.invalidation)
    if stop_mode == "setup":
        if d == 1:
            stop = inv - 0.05 * a
            risk = ep - stop
        else:
            stop = inv + 0.05 * a
            risk = stop - ep
    elif stop_mode == "1.0atr":
        risk = a
        stop = ep - d * risk
    else:
        risk = 1.5 * a
        stop = ep - d * risk
    risk = max(risk, 0.25 * a)
    target = ep + d * target_r * risk
    peak = 0.0
    exit_r = 0.0
    collisions = 0
    for k in range(ei, min(ei + 60, m.n)):
        hi, lo = float(m.hi[k]), float(m.lo[k])
        fav = (hi - ep) * d / risk
        peak = max(peak, fav)
        hs = lo <= stop if d == 1 else hi >= stop
        ht = hi >= target if d == 1 else lo <= target
        if hs and ht:
            collisions += 1
            exit_r = -1.0
            break
        if hs:
            exit_r = (stop - ep) * d / risk
            break
        if ht:
            exit_r = target_r
            break
    else:
        cl = float(m.cl[min(ei + 59, m.n - 1)])
        exit_r = (cl - ep) * d / risk
    cost = NQ.cost_r(ep, stop) * cost_mult
    net_r = exit_r - cost
    return {
        "gross_R": exit_r, "cost_R": cost, "net_R": net_r,
        "risk_atr": risk / a, "collisions": collisions,
        "max_mfe_R": peak,
    }


def summarize_sim(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"N": 0, "AvgR": 0, "PF": 0, "TotalR": 0, "MaxDD": 0}
    m = metrics(df["net_R"].values)
    m["gross_AvgR"] = float(df["gross_R"].mean())
    m["gross_TotalR"] = float(df["gross_R"].sum())
    m["avg_cost_R"] = float(df["cost_R"].mean())
    m["median_risk_atr"] = float(df["risk_atr"].median())
    return m
