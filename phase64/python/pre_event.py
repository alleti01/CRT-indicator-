"""Phase64 — causal pre-event state features."""
from __future__ import annotations

import numpy as np
import pandas as pd


def pre_event_features(hi, lo, cl, op, atr, event_is: np.ndarray) -> pd.DataFrame:
    """Causal descriptors available at event bar close."""
    rows = []
    for ei in event_is:
        ei = int(ei)
        a = float(atr[ei]) if np.isfinite(atr[ei]) and atr[ei] > 0 else 1.0
        ep = float(op[ei])

        def _range(n):
            s = max(0, ei - n)
            r = (np.max(hi[s:ei + 1]) - np.min(lo[s:ei + 1])) / a if ei > s else 0.0
            return r

        r5, r10, r15 = _range(5), _range(10), _range(15)
        r30 = _range(30)

        def _dist_extreme(n):
            s = max(0, ei - n)
            hi_n = float(np.max(hi[s:ei + 1]))
            lo_n = float(np.min(lo[s:ei + 1]))
            return (hi_n - ep) / a, (ep - lo_n) / a

        d_hi5, d_lo5 = _dist_extreme(5)
        d_hi15, d_lo15 = _dist_extreme(15)
        d_hi30, d_lo30 = _dist_extreme(30)

        # Range position in 15-bar window
        s15 = max(0, ei - 15)
        hi15, lo15 = float(np.max(hi[s15:ei + 1])), float(np.min(lo[s15:ei + 1]))
        rng15 = hi15 - lo15
        range_pos = (ep - lo15) / rng15 if rng15 > 0 else 0.5
        if range_pos >= 0.67:
            edge = "UPPER"
        elif range_pos <= 0.33:
            edge = "LOWER"
        else:
            edge = "MIDDLE"

        # Recent displacement
        if ei >= 3:
            disp = abs(cl[ei] - cl[ei - 3]) / a
        else:
            disp = 0.0

        # Chop: sum of |bar ranges| / net range over 10 bars
        s10 = max(0, ei - 9)
        bar_ranges = hi[s10:ei + 1] - lo[s10:ei + 1]
        net = abs(cl[ei] - cl[s10]) if ei > s10 else 1.0
        chop = float(np.sum(bar_ranges) / max(net, a * 0.01))

        rows.append({
            "event_i": ei,
            "pre_r5": r5,
            "pre_r10": r10,
            "pre_r15": r15,
            "pre_r30": r30,
            "pre_atr": a,
            "dist_hi5": d_hi5,
            "dist_lo5": d_lo5,
            "dist_hi15": d_hi15,
            "dist_lo15": d_lo15,
            "dist_hi30": d_hi30,
            "dist_lo30": d_lo30,
            "range_edge": edge,
            "displacement_3": disp,
            "chop_10": chop,
            "compression_5_15": r5 / r15 if r15 > 0 else 1.0,
        })
    return pd.DataFrame(rows)


def compare_pre_event(phase58: pd.DataFrame, control: pd.DataFrame) -> dict:
    out = {}
    for col in ["pre_r5", "pre_r10", "pre_r15", "compression_5_15", "chop_10"]:
        if col in phase58.columns and col in control.columns:
            p = float(phase58[col].median())
            c = float(control[col].median())
            out[col] = {"phase58": p, "control": c, "lift": p / c if c > 0 else 0}
    for edge in ("UPPER", "LOWER", "MIDDLE"):
        out[f"edge_{edge}_p58"] = float((phase58["range_edge"] == edge).mean())
        out[f"edge_{edge}_ctl"] = float((control["range_edge"] == edge).mean())
    return out
