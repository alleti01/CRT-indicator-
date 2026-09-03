"""Phase67 — path metrics, DAS, simulation."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ
from phase58b.research.simulation import metrics
from phase62.python.analysis import path_ordering
from phase67.python.families import SetupSignal
from phase67.python.precompute import MarketPre


PAIR_KEYS = [
    "+0.5_before_-0.5", "+1_before_-1", "+1.5_before_-1", "+2_before_-1",
    "+2.5_before_-1", "+3_before_-1", "+1_before_-1.5", "+2_before_-1.5",
    "+2.5_before_-1.5", "+3_before_-1.5", "+2_before_-2", "+3_before_-2",
]


def _extended_pairs(po: dict) -> dict:
    times = po["times"]

    def before(pos, neg):
        tp, tn = times.get(f"+{pos}"), times.get(f"-{neg}")
        if tp is None and tn is None:
            return None
        if tp is None:
            return False
        if tn is None:
            return True
        return tp < tn

    return {
        "+0.5_before_-0.5": before(0.5, 0.5),
        "+1_before_-1": before(1.0, 1.0),
        "+1.5_before_-1": before(1.5, 1.0),
        "+2_before_-1": before(2.0, 1.0),
        "+2.5_before_-1": before(2.5, 1.0),
        "+3_before_-1": before(3.0, 1.0),
        "+1_before_-1.5": before(1.0, 1.5),
        "+2_before_-1.5": before(2.0, 1.5),
        "+2.5_before_-1.5": before(2.5, 1.5),
        "+3_before_-1.5": before(3.0, 1.5),
        "+2_before_-2": before(2.0, 2.0),
        "+3_before_-2": before(3.0, 2.0),
    }


def path_from_signal(p: MarketPre, sig: SetupSignal, max_h: int = 60) -> dict:
    ei = sig.entry_i
    ep = float(p.op[ei])
    a = float(p.atr[ei]) if p.atr[ei] > 0 else 1.0
    d = 1 if sig.direction == "LONG" else -1
    end = min(ei + max_h, p.n)
    hs, ls = p.hi[ei:end], p.lo[ei:end]
    if d == 1:
        fav = (np.maximum.accumulate(hs) - ep) / a
        adv = (ep - np.minimum.accumulate(ls)) / a
    else:
        fav = (ep - np.minimum.accumulate(ls)) / a
        adv = (np.maximum.accumulate(hs) - ep) / a
    po = path_ordering(p.hi, p.lo, p.op, ei, sig.direction, a, max_h)
    pairs = _extended_pairs(po)
    out = {"pairs": pairs, "times": po["times"]}
    for h in [3, 5, 10, 15, 30, 60]:
        sl = min(h, len(fav))
        out[f"mfe_{h}m"] = float(np.max(fav[:sl])) if sl else 0.0
        out[f"mae_{h}m"] = float(np.max(adv[:sl])) if sl else 0.0
    # remaining excursion: share of 60m MFE left at entry (entry at start → ~100%)
    total_fav = float(np.max(fav)) if len(fav) else 0.0
    out["remaining_mfe_pct"] = 1.0  # entered at trigger; chase captured separately
    out["chase_atr"] = sig.chase_atr
    out["delay_bars"] = sig.delay_bars
    return out


def aggregate_paths(paths: list[dict]) -> dict:
    if not paths:
        return {"n": 0}
    pairs_acc, totals = {}, {}
    mfes, maes = {}, {}
    for h in [3, 5, 10, 15, 30, 60]:
        mfes[h], maes[h] = [], []
    delays, chases, risks = [], [], []
    for pth in paths:
        for k in PAIR_KEYS:
            v = pth.get("pairs", {}).get(k)
            if v is None:
                continue
            totals[k] = totals.get(k, 0) + 1
            if v:
                pairs_acc[k] = pairs_acc.get(k, 0) + 1
        for h in [3, 5, 10, 15, 30, 60]:
            mfes[h].append(pth.get(f"mfe_{h}m", 0))
            maes[h].append(pth.get(f"mae_{h}m", 0))
        delays.append(pth.get("delay_bars", 0))
        chases.append(pth.get("chase_atr", 0))
        if "risk_atr" in pth:
            risks.append(pth["risk_atr"])
    out = {"n": len(paths)}
    for k, t in totals.items():
        out[k] = pairs_acc.get(k, 0) / t
    for h in [3, 5, 10, 15, 30, 60]:
        out[f"median_mfe_{h}m"] = float(np.median(mfes[h])) if mfes[h] else 0
        out[f"median_mae_{h}m"] = float(np.median(maes[h])) if maes[h] else 0
        mm = out[f"median_mfe_{h}m"]
        ma = out[f"median_mae_{h}m"]
        out[f"das_{h}m"] = mm / ma if ma > 0 else 0
    out["median_delay"] = float(np.median(delays)) if delays else 0
    out["median_chase"] = float(np.median(chases)) if chases else 0
    if risks:
        out["median_stop_atr"] = float(np.median(risks))
    return out


def simulate_signal(p: MarketPre, sig: SetupSignal, target_r: float = 2.0,
                    cost_mult: float = 1.0, max_hold: int = 60) -> dict:
    ei = sig.entry_i
    d = 1 if sig.direction == "LONG" else -1
    ep = float(p.op[ei])
    a = float(p.atr[ei]) if p.atr[ei] > 0 else 1.0
    inv = float(sig.invalidation)
    if d == 1:
        stop = inv - 0.05 * a
        risk = ep - stop
    else:
        stop = inv + 0.05 * a
        risk = stop - ep
    risk = max(risk, 0.25 * a)
    target = ep + d * target_r * risk
    exit_r = 0.0
    collisions = 0
    for k in range(ei, min(ei + max_hold, p.n)):
        hi, lo = float(p.hi[k]), float(p.lo[k])
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
        cl = float(p.cl[min(ei + max_hold - 1, p.n - 1)])
        exit_r = (cl - ep) * d / risk
    cost = NQ.cost_r(ep, stop) * cost_mult
    return {
        "gross_R": exit_r, "cost_R": cost, "net_R": exit_r - cost,
        "risk_atr": risk / a, "collisions": collisions,
    }


def summarize_sim(rows: list[dict]) -> dict:
    if not rows:
        return {"N": 0, "AvgR": 0, "PF": 0, "TotalR": 0, "MaxDD": 0}
    df = pd.DataFrame(rows)
    m = metrics(df["net_R"].values)
    m["gross_AvgR"] = float(df["gross_R"].mean())
    m["gross_TotalR"] = float(df["gross_R"].sum())
    m["avg_cost_R"] = float(df["cost_R"].mean())
    m["median_risk_atr"] = float(df["risk_atr"].median())
    return m


def early_gate(path_agg: dict, sim: dict) -> tuple[bool, str]:
    """Return (pass, reason)."""
    n = path_agg.get("n", 0)
    if n < 500:
        return False, "LOW_SAMPLE"
    po1 = path_agg.get("+1_before_-1", 0.5)
    po2 = path_agg.get("+2_before_-1", 0.33)
    das15 = path_agg.get("das_15m", 1.0)
    stop = sim.get("median_risk_atr", 1.0)
    cost = sim.get("avg_cost_R", 0)
    if 0.47 <= po1 <= 0.53 and po2 <= 0.36 and abs(das15 - 1.0) < 0.15:
        return False, "SYMMETRIC_NO_EDGE"
    if stop < 0.5 and cost > 0.8:
        return False, "FRICTION_IMPRACTICAL"
    if po2 >= 0.38 or (po1 >= 0.52 and das15 >= 1.15):
        return True, "INTERESTING"
    if po2 >= 0.35 and das15 >= 1.1:
        return True, "MARGINAL"
    return False, "WEAK_PATH"
