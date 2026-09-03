"""Phase64 — direction-neutral symmetric path metrics from location origin."""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = [1, 2, 3, 5, 10, 15, 30, 60]
THRESHOLDS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]


def _first_ge(arr: np.ndarray, thr: float) -> int | None:
    hit = np.where(arr >= thr)[0]
    return int(hit[0] + 1) if len(hit) else None


def compute_single_path(hi, lo, op, event_i: int, atr: float, max_h: int = 60) -> dict:
    """Symmetric forward path from event bar origin."""
    a = atr if atr > 0 else 1.0
    ep = float(op[event_i])
    end = min(event_i + max_h, len(hi))
    hs = hi[event_i:end].astype(float)
    ls = lo[event_i:end].astype(float)
    if len(hs) == 0:
        return {}

    up = (np.maximum.accumulate(hs) - ep) / a
    dn = (ep - np.minimum.accumulate(ls)) / a
    n_bars = len(up)

    out: dict = {"event_i": event_i, "origin": ep, "atr": a}
    for h in HORIZONS:
        if h <= n_bars:
            sl = slice(0, h)
            out[f"up_{h}m"] = float(np.max(up[sl]))
            out[f"dn_{h}m"] = float(np.max(dn[sl]))
            out[f"abs_{h}m"] = float(max(np.max(up[sl]), np.max(dn[sl])))
            out[f"range_{h}m"] = float((np.max(hs[sl]) - np.min(ls[sl])) / a)
        else:
            out[f"up_{h}m"] = float(np.max(up))
            out[f"dn_{h}m"] = float(np.max(dn))
            out[f"abs_{h}m"] = float(max(np.max(up), np.max(dn)))
            out[f"range_{h}m"] = float((np.max(hs) - np.min(ls)) / a)

    out["up_60m"] = float(np.max(up))
    out["dn_60m"] = float(np.max(dn))
    out["abs_60m"] = float(max(np.max(up), np.max(dn)))
    out["range_60m"] = float((np.max(hs) - np.min(ls)) / a)

    t_up, t_dn = {}, {}
    for thr in THRESHOLDS:
        t_up[thr] = _first_ge(up, thr)
        t_dn[thr] = _first_ge(dn, thr)
        out[f"t_up_{thr}"] = t_up[thr]
        out[f"t_dn_{thr}"] = t_dn[thr]
        out[f"hit_either_{thr}"] = t_up[thr] is not None or t_dn[thr] is not None
        out[f"hit_both_{thr}"] = t_up[thr] is not None and t_dn[thr] is not None

    # First side at key levels
    for thr in [0.5, 1.0, 1.5, 2.0]:
        tu, td = t_up.get(thr), t_dn.get(thr)
        if tu is None and td is None:
            out[f"first_{thr}"] = "NEITHER"
        elif tu is not None and (td is None or tu < td):
            out[f"first_{thr}"] = "UP"
        elif td is not None and (tu is None or td < tu):
            out[f"first_{thr}"] = "DOWN"
        else:
            out[f"first_{thr}"] = "TIE"

    # Continuation after first ±0.5
    out.update(_continuation_stats(up, dn, t_up, t_dn, 0.5))
    out.update(_continuation_stats(up, dn, t_up, t_dn, 1.0, prefix="1.0"))

    # Cleanliness
    net = (float(hs[-1]) - ep) / a if len(hs) else 0.0
    total_range = out["range_60m"]
    out["net_disp"] = net
    out["net_over_range"] = abs(net) / total_range if total_range > 0 else 0.0
    out["largest_over_range"] = out["abs_60m"] / total_range if total_range > 0 else 0.0
    out["clean_up"] = out["up_60m"] >= 2.0 and out["dn_60m"] < 1.0
    out["clean_dn"] = out["dn_60m"] >= 2.0 and out["up_60m"] < 1.0
    out["large_chaotic"] = out["up_60m"] >= 2.0 and out["dn_60m"] >= 2.0

    out["archetype"] = classify_archetype(out)
    return out


def _continuation_stats(up, dn, t_up, t_dn, thr: float, prefix: str = "0.5") -> dict:
    """After first break at ±thr, measure continuation vs failure."""
    tu, td = t_up.get(thr), t_dn.get(thr)
    out = {}
    if tu is not None and (td is None or tu <= td):
        first = "UP"
        start = tu - 1
    elif td is not None:
        first = "DOWN"
        start = td - 1
    else:
        out[f"cont_{prefix}_first"] = None
        return out

    out[f"cont_{prefix}_first"] = first
    sub_up = up[start:]
    sub_dn = dn[start:]
    if first == "UP":
        out[f"cont_{prefix}_reach_1"] = _first_ge(sub_up, 1.0) is not None
        out[f"cont_{prefix}_reach_15"] = _first_ge(sub_up, 1.5) is not None
        out[f"cont_{prefix}_reach_2"] = _first_ge(sub_up, 2.0) is not None
        fail = _first_ge(sub_dn, 1.0)
        reach2 = _first_ge(sub_up, 2.0)
        out[f"cont_{prefix}_fail"] = fail is not None and (reach2 is None or fail < reach2)
    else:
        out[f"cont_{prefix}_reach_1"] = _first_ge(sub_dn, 1.0) is not None
        out[f"cont_{prefix}_reach_15"] = _first_ge(sub_dn, 1.5) is not None
        out[f"cont_{prefix}_reach_2"] = _first_ge(sub_dn, 2.0) is not None
        fail = _first_ge(sub_up, 1.0)
        reach2 = _first_ge(sub_dn, 2.0)
        out[f"cont_{prefix}_fail"] = fail is not None and (reach2 is None or fail < reach2)
    return out


def classify_archetype(p: dict) -> str:
    """Retrospective descriptive path class — fixed rules, no optimization."""
    up2, dn2 = p.get("up_60m", 0), p.get("dn_60m", 0)
    t_up05 = p.get("t_up_0.5")
    t_dn05 = p.get("t_dn_0.5")
    t_up1 = p.get("t_up_1.0")
    t_dn1 = p.get("t_dn_1.0")

    if up2 < 0.5 and dn2 < 0.5:
        return "COMPRESSION_NO_EXPANSION"

    if t_up1 is not None and t_up1 <= 3 and up2 >= 2.0 and dn2 < 1.0:
        return "EXPLOSIVE_IMMEDIATE_MOVE"
    if t_dn1 is not None and t_dn1 <= 3 and dn2 >= 2.0 and up2 < 1.0:
        return "EXPLOSIVE_IMMEDIATE_MOVE"

    hit_both_1 = p.get("hit_both_1.0", False)
    if hit_both_1:
        second = max(t_up1 or 999, t_dn1 or 999)
        if second >= 30:
            return "LATE_EXPANSION"
        post_up = up2 - 1.0 if up2 > 1 else 0
        post_dn = dn2 - 1.0 if dn2 > 1 else 0
        if post_up >= 1.5 and post_up > post_dn:
            return "TWO_SIDED_SWEEP_THEN_UP"
        if post_dn >= 1.5 and post_dn > post_up:
            return "TWO_SIDED_SWEEP_THEN_DOWN"
        return "TWO_SIDED_CHOP"

    if p.get("first_0.5") == "UP":
        if p.get("cont_0.5_fail"):
            return "UP_BREAK_FAILURE_TO_DOWN"
        if p.get("cont_0.5_reach_2"):
            return "UP_BREAK_CONTINUATION"
    if p.get("first_0.5") == "DOWN":
        if p.get("cont_0.5_fail"):
            return "DOWN_BREAK_FAILURE_TO_UP"
        if p.get("cont_0.5_reach_2"):
            return "DOWN_BREAK_CONTINUATION"

    if up2 >= 2.0 and dn2 < 1.0:
        return "CLEAN_UP_EXPANSION"
    if dn2 >= 2.0 and up2 < 1.0:
        return "CLEAN_DOWN_EXPANSION"

    if up2 >= 1.5 or dn2 >= 1.5:
        return "LATE_EXPANSION"
    return "TWO_SIDED_CHOP"


def compute_paths_batch(hi, lo, op, event_is: np.ndarray, atrs: np.ndarray, max_h: int = 60) -> pd.DataFrame:
    rows = []
    for ei, atr in zip(event_is, atrs):
        if ei < 0 or ei >= len(hi) - max_h - 1:
            continue
        rows.append(compute_single_path(hi, lo, op, int(ei), float(atr), max_h))
    return pd.DataFrame(rows)


def either_side_prob(df: pd.DataFrame, thr: float, horizon: int) -> float:
    col = f"abs_{horizon}m"
    if col not in df.columns:
        return 0.0
    return float((df[col] >= thr).mean())


def median_time_either(df: pd.DataFrame, thr: float) -> float:
    tu = df.get(f"t_up_{thr}", pd.Series(dtype=float))
    td = df.get(f"t_dn_{thr}", pd.Series(dtype=float))
    times = []
    for a, b in zip(tu, td):
        vals = [x for x in (a, b) if x is not None and not (isinstance(x, float) and np.isnan(x))]
        if vals:
            times.append(min(vals))
    return float(np.median(times)) if times else float("nan")


def summarize_paths(df: pd.DataFrame) -> dict:
    """Aggregate symmetric path metrics."""
    if df.empty:
        return {"n": 0}
    s: dict = {"n": len(df)}
    for h in [5, 10, 15, 30, 60]:
        for side in ("up", "dn", "abs", "range"):
            col = f"{side}_{h}m"
            if col in df.columns:
                s[f"median_{col}"] = float(df[col].median())
                s[f"mean_{col}"] = float(df[col].mean())

    for h in [15, 30, 60]:
        for thr in THRESHOLDS:
            s[f"p_either_{thr}_within_{h}m"] = float((df[f"abs_{h}m"] >= thr).mean())

    for thr in THRESHOLDS:
        s[f"median_t_either_{thr}"] = median_time_either(df, thr)
        s[f"p_hit_both_{thr}"] = float(df[f"hit_both_{thr}"].mean()) if f"hit_both_{thr}" in df.columns else 0

    for thr in [0.5, 1.0]:
        col = f"first_{thr}"
        if col in df.columns:
            vc = df[col].value_counts(normalize=True)
            s[f"p_up_first_{thr}"] = float(vc.get("UP", 0))
            s[f"p_dn_first_{thr}"] = float(vc.get("DOWN", 0))
            s[f"p_neither_{thr}"] = float(vc.get("NEITHER", 0))

    for prefix in ("0.5", "1.0"):
        sub = df[df[f"cont_{prefix}_first"] == "UP"]
        if len(sub):
            s[f"after_up_{prefix}_reach_2"] = float(sub[f"cont_{prefix}_reach_2"].mean())
            s[f"after_up_{prefix}_fail"] = float(sub[f"cont_{prefix}_fail"].mean())
        sub = df[df[f"cont_{prefix}_first"] == "DOWN"]
        if len(sub):
            s[f"after_dn_{prefix}_reach_2"] = float(sub[f"cont_{prefix}_reach_2"].mean())
            s[f"after_dn_{prefix}_fail"] = float(sub[f"cont_{prefix}_fail"].mean())

    s["median_net_over_range"] = float(df["net_over_range"].median())
    s["median_largest_over_range"] = float(df["largest_over_range"].median())
    s["p_clean_up"] = float(df["clean_up"].mean())
    s["p_clean_dn"] = float(df["clean_dn"].mean())
    s["p_large_chaotic"] = float(df["large_chaotic"].mean())

    if "archetype" in df.columns:
        vc = df["archetype"].value_counts(normalize=True)
        for arch in vc.index:
            s[f"arch_{arch}"] = float(vc[arch])
    return s
