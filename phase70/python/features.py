"""Phase70 — causal signal-time extension and chase features."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _atr(v: float, fallback: float = 1.0) -> float:
    return v if v and v > 0 else fallback


def compute_signal_features(
    si: int,
    direction: str,
    hi, lo, cl, op,
    atr: float,
    entry_i: int,
    entry_price: float,
    ts=None,
) -> dict:
    """Features known at signal bar close (index si). No future bars."""
    d = 1 if direction == "LONG" else -1
    atr = _atr(atr)
    si = int(si)
    n = len(cl)
    si = min(max(si, 0), n - 1)
    sig_close = float(cl[si])

    out: dict = {"signal_i": si, "signal_close": sig_close, "known_at": si}

    for w in [1, 3, 5, 10, 15]:
        i0 = max(0, si - w + 1)
        out[f"move_{w}m_atr"] = (float(cl[si]) - float(cl[i0])) * d / atr

    chases = []
    for nb in [3, 5, 10]:
        i0 = max(0, si - nb + 1)
        window_hi = hi[i0 : si + 1]
        window_lo = lo[i0 : si + 1]
        if d == 1:
            ref = float(np.min(window_lo))
            dist = (sig_close - ref) / atr
        else:
            ref = float(np.max(window_hi))
            dist = (ref - sig_close) / atr
        out[f"dist_from_{nb}bar_extreme_atr"] = dist
        chases.append(dist)

    out["chase_distance_atr"] = float(max(chases))

    # Same-direction bar count in last 3/5/8
    for nb in [3, 5, 8]:
        i0 = max(0, si - nb + 1)
        cnt = 0
        for k in range(i0, si + 1):
            if k == 0:
                continue
            bar_dir = 1 if cl[k] > cl[k - 1] else -1 if cl[k] < cl[k - 1] else 0
            if bar_dir == d:
                cnt += 1
        out[f"same_dir_bars_{nb}"] = cnt

    body = abs(float(cl[si]) - float(op[si]))
    out["body_atr"] = body / atr

    # Recent range traversed (causal window 10 bars)
    i0 = max(0, si - 9)
    rng = float(np.max(hi[i0 : si + 1]) - np.min(lo[i0 : si + 1]))
    if rng > 0:
        if d == 1:
            out["pct_range_traversed"] = (sig_close - float(np.min(lo[i0 : si + 1]))) / rng
        else:
            out["pct_range_traversed"] = (float(np.max(hi[i0 : si + 1])) - sig_close) / rng
    else:
        out["pct_range_traversed"] = 0.5

    # PASS_CHASE: signal close → executable entry
    if entry_i < n:
        entry_px = float(entry_price) if entry_price else float(op[entry_i])
        out["entry_slippage_atr"] = (entry_px - sig_close) * d / atr
        out["signal_to_entry_atr"] = abs(entry_px - sig_close) / atr
    else:
        out["entry_slippage_atr"] = 0.0
        out["signal_to_entry_atr"] = 0.0

    return out


def extension_band(chase: float, q25: float, q50: float, q75: float) -> str:
    if chase <= q25:
        return "LOW_EXTENSION"
    if chase <= q50:
        return "MEDIUM_EXTENSION"
    if chase <= q75:
        return "HIGH_EXTENSION"
    return "EXTREME_EXTENSION"


def batch_signal_features(execs: pd.DataFrame, m) -> pd.DataFrame:
    rows = []
    for _, ex in execs.iterrows():
        si = int(ex["signal_i"])
        if si >= m.n - 2:
            continue
        f = compute_signal_features(
            si, ex["direction"], m.hi, m.lo, m.cl, m.op,
            float(ex["atr_entry"]), int(ex["entry_i"]), float(ex["entry_price"]),
            ex.get("entry_ts"),
        )
        f["trade_id"] = ex["trade_id"]
        f["direction"] = ex["direction"]
        rows.append(f)
    return pd.DataFrame(rows)
