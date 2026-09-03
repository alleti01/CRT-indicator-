"""Phase68 — path metrics from trade tape + 1m bars."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ
from phase58b.research.simulation import metrics


def path_from_entry_m1(m1: pd.DataFrame, entry_ts: pd.Timestamp, direction: str, atr: float,
                       horizons_min=(1, 2, 5, 10, 15)) -> dict:
    idx = m1.index.searchsorted(entry_ts)
    if idx >= len(m1):
        return {}
    ep = float(m1.iloc[idx]["open"])
    a = atr if atr > 0 else 1.0
    d = 1 if direction == "LONG" else -1
    out = {}
    pairs_acc, totals = {}, {}
    end_max = min(idx + 16, len(m1))
    hs = m1["high"].iloc[idx:end_max].to_numpy()
    ls = m1["low"].iloc[idx:end_max].to_numpy()
    if d == 1:
        fav = (np.maximum.accumulate(hs) - ep) / a
        adv = (ep - np.minimum.accumulate(ls)) / a
    else:
        fav = (ep - np.minimum.accumulate(ls)) / a
        adv = (np.maximum.accumulate(hs) - ep) / a

    def before(pt, nt):
        tp = next((i + 1 for i, v in enumerate(fav) if v >= pt), None)
        tn = next((i + 1 for i, v in enumerate(adv) if v >= nt), None)
        if tp is None and tn is None:
            return None
        if tp is None:
            return False
        if tn is None:
            return True
        return tp < tn

    for pname, pt, nt in [
        ("+0.5_before_-0.5", 0.5, 0.5), ("+1_before_-1", 1.0, 1.0),
        ("+1.5_before_-1", 1.5, 1.0), ("+2_before_-1", 2.0, 1.0),
        ("+2_before_-1.5", 2.0, 1.5),
    ]:
        v = before(pt, nt)
        if v is not None:
            totals[pname] = totals.get(pname, 0) + 1
            if v:
                pairs_acc[pname] = pairs_acc.get(pname, 0) + 1
    for h in horizons_min:
        sl = min(h, len(fav))
        out[f"mfe_{h}m"] = float(np.max(fav[:sl])) if sl else 0
        out[f"mae_{h}m"] = float(np.max(adv[:sl])) if sl else 0
    out["pairs"] = {k: pairs_acc.get(k, 0) / totals[k] for k in totals}
    out["direction_correct_5m"] = float(m1.iloc[min(idx + 4, len(m1) - 1)]["close"] > ep) if d == 1 else float(m1.iloc[min(idx + 4, len(m1) - 1)]["close"] < ep)
    return out


def aggregate_paths(paths: list[dict]) -> dict:
    if not paths:
        return {"n": 0}
    out = {"n": len(paths)}
    pairs_acc, totals = {}, {}
    mfes, maes = {}, {}
    for p in paths:
        for k, v in p.get("pairs", {}).items():
            totals[k] = totals.get(k, 0) + 1
            if v:
                pairs_acc[k] = pairs_acc.get(k, 0) + 1
        for h in [1, 2, 5, 10, 15]:
            mfes.setdefault(h, []).append(p.get(f"mfe_{h}m", 0))
            maes.setdefault(h, []).append(p.get(f"mae_{h}m", 0))
    for k, t in totals.items():
        out[k] = pairs_acc.get(k, 0) / t
    for h in mfes:
        out[f"median_mfe_{h}m"] = float(np.median(mfes[h]))
        out[f"median_mae_{h}m"] = float(np.median(maes[h]))
        mm, ma = out[f"median_mfe_{h}m"], out[f"median_mae_{h}m"]
        out[f"das_{h}m"] = mm / ma if ma > 0 else 0
    out["direction_acc_5m"] = float(np.mean([p.get("direction_correct_5m", 0) for p in paths]))
    return out


def simulate_m1(m1: pd.DataFrame, entry_ts: pd.Timestamp, direction: str, atr: float,
                stop_atr: float = 1.0, target_r: float = 2.0, max_hold: int = 15,
                cost_mult: float = 1.0) -> dict:
    idx = m1.index.searchsorted(entry_ts)
    if idx >= len(m1):
        return {"gross_R": 0, "cost_R": 0, "net_R": 0, "risk_atr": stop_atr}
    ep = float(m1.iloc[idx]["open"])
    a = atr if atr > 0 else 1.0
    d = 1 if direction == "LONG" else -1
    risk = stop_atr * a
    stop = ep - d * risk
    target = ep + d * target_r * risk
    exit_r = 0.0
    for k in range(idx, min(idx + max_hold, len(m1))):
        hi, lo = float(m1.iloc[k]["high"]), float(m1.iloc[k]["low"])
        hs = lo <= stop if d == 1 else hi >= stop
        ht = hi >= target if d == 1 else lo <= target
        if hs and ht:
            exit_r = -1.0
            break
        if hs:
            exit_r = -1.0
            break
        if ht:
            exit_r = target_r
            break
    else:
        cl = float(m1.iloc[min(idx + max_hold - 1, len(m1) - 1)]["close"])
        exit_r = (cl - ep) * d / risk
    cost = NQ.cost_r(ep, stop) * cost_mult
    return {"gross_R": exit_r, "cost_R": cost, "net_R": exit_r - cost, "risk_atr": stop_atr}


def summarize_sim(rows: list[dict]) -> dict:
    if not rows:
        return {"N": 0, "AvgR": 0, "PF": 0, "TotalR": 0}
    df = pd.DataFrame(rows)
    m = metrics(df["net_R"].values)
    m["gross_AvgR"] = float(df["gross_R"].mean())
    m["avg_cost_R"] = float(df["cost_R"].mean())
    return m
