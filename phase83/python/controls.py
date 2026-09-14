"""Random direction, flipped direction, timing-matched, and level controls."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase83.python.management import walk_m0
from phase83.python.metrics import summarize


def random_and_flipped(trades: pd.DataFrame, arr: dict, seeds: int = 20) -> dict:
    if trades.empty:
        return {"real": {}, "random": {}, "flipped": {}}
    hi, lo, cl = arr["hi"], arr["lo"], arr["cl"]
    real = summarize(trades)
    # Flipped: opposite direction, re-walk M0 from same entry
    flip_rs = []
    for _, r in trades.iterrows():
        opp = "SHORT" if r["direction"] == "LONG" else "LONG"
        w = walk_m0(hi, lo, cl, entry_i=int(r["entry_i"]), direction=opp, entry_price=float(r["entry_price"]), atr=float(r["atr"]))
        flip_rs.append(w["net_r"])
    flip_df = trades.copy()
    flip_df["net_r"] = flip_rs
    flip_df["gross_r"] = flip_rs
    flipped = summarize(flip_df)

    rnd_avgs = []
    rng = np.random.default_rng(83)
    for s in range(seeds):
        rs = []
        rr = np.random.default_rng(s)
        for _, r in trades.iterrows():
            d = "LONG" if rr.random() < 0.5 else "SHORT"
            w = walk_m0(hi, lo, cl, entry_i=int(r["entry_i"]), direction=d, entry_price=float(r["entry_price"]), atr=float(r["atr"]))
            rs.append(w["net_r"])
        rs = np.asarray(rs, dtype=float)
        rs = rs[np.isfinite(rs)]
        if len(rs):
            rnd_avgs.append(float(rs.mean()))
    random = {
        "N": int(len(trades)),
        "AvgR": float(np.mean(rnd_avgs)) if rnd_avgs else float("nan"),
        "AvgR_p2.5": float(np.percentile(rnd_avgs, 2.5)) if rnd_avgs else float("nan"),
        "AvgR_p97.5": float(np.percentile(rnd_avgs, 97.5)) if rnd_avgs else float("nan"),
        "seeds": seeds,
    }
    return {"real": real, "random": random, "flipped": flipped, "real_gt_random": real.get("AvgR", 0) > random.get("AvgR", 0)}


def timing_matched(trades: pd.DataFrame, arr: dict, sessions, n_per: int = 1, seed: int = 7) -> dict:
    """Random timestamps in same session + time bucket; random direction; same ATR env."""
    if trades.empty:
        return {"N": 0}
    rng = np.random.default_rng(seed)
    by_date = {s.date: s for s in sessions}
    hi, lo, cl, ny = arr["hi"], arr["lo"], arr["cl"], arr["ny"]
    rows = []
    from phase83.python.levels import time_bucket

    for _, r in trades.iterrows():
        sess = by_date.get(r["date"])
        if sess is None:
            continue
        bucket = r["time_bucket"]
        cands = []
        for i in range(sess.rth_open_i, sess.research_end_i + 1):
            ts = ny[i]
            if time_bucket(int(ts.hour), int(ts.minute)) != bucket:
                continue
            a = float(arr["atr"][i])
            if not np.isfinite(a) or a <= 0:
                continue
            if abs(a - float(r["atr"])) / float(r["atr"]) > 0.35:
                continue
            if i + 1 >= arr["n"] - 2:
                continue
            cands.append(i)
        if not cands:
            continue
        i = int(rng.choice(cands))
        d = "LONG" if rng.random() < 0.5 else "SHORT"
        w = walk_m0(hi, lo, cl, entry_i=i + 1, direction=d, entry_price=float(arr["op"][i + 1]), atr=float(arr["atr"][i]))
        rows.append(w["net_r"])
    if not rows:
        return {"N": 0}
    s = pd.Series(rows, dtype=float)
    return {"N": int(s.notna().sum()), "AvgR": float(s.mean()), "TotalR": float(s.sum()), "WinRate": float((s > 0).mean())}
