"""Evaluation labels — future data used ONLY here, never for clustering."""
from __future__ import annotations

import numpy as np
import pandas as pd


def label_meaningful_moves(
    opps: pd.DataFrame,
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    atr: np.ndarray,
    horizons: tuple[int, ...] = (30, 60),
    thresholds: tuple[float, ...] = (0.5, 1.0, 1.5, 2.0, 2.5),
) -> pd.DataFrame:
    """Future excursion labels per opportunity (evaluation only)."""
    rows = []
    n = len(cl)
    for _, o in opps.iterrows():
        si = int(o["first_signal_i"])
        d = o["direction"]
        a = _atr(atr, si)
        row = {"opportunity_id": o["opportunity_id"], "direction": d, "first_signal_i": si}
        for h in horizons:
            end = min(n, si + 1 + h)
            if end <= si + 1:
                continue
            if d == "LONG":
                mfe = (hi[si + 1 : end].max() - cl[si]) / a
                mae = (cl[si] - lo[si + 1 : end].min()) / a
            else:
                mfe = (cl[si] - lo[si + 1 : end].min()) / a
                mae = (hi[si + 1 : end].max() - cl[si]) / a
            row[f"mfe_{h}m_atr"] = mfe
            row[f"mae_{h}m_atr"] = mae
            for thr in thresholds:
                row[f"meaningful_{thr}atr_{h}m"] = mfe >= thr
        rows.append(row)
    return pd.DataFrame(rows)


def move_capture_at_entry(
    signal_i: int,
    entry_i: int,
    direction: str,
    hi: np.ndarray,
    lo: np.ndarray,
    cl: np.ndarray,
    atr: np.ndarray,
    horizon: int = 60,
) -> dict:
    """Label-only move capture."""
    a = _atr(atr, signal_i)
    end = min(len(cl), signal_i + 1 + horizon)
    if end <= signal_i + 1:
        return {"capture_pct": np.nan, "mfe_spent_atr": np.nan}
    if direction == "LONG":
        total = (hi[signal_i + 1 : end].max() - cl[signal_i]) / a
        spent = max(0, (cl[entry_i] - cl[signal_i]) / a) if entry_i < len(cl) else 0
    else:
        total = (cl[signal_i] - lo[signal_i + 1 : end].min()) / a
        spent = max(0, (cl[signal_i] - cl[entry_i]) / a) if entry_i < len(cl) else 0
    cap = (total - spent) / total if total > 0 else np.nan
    return {"capture_pct": cap, "mfe_spent_atr": spent, "total_mfe_atr": total}


def price_bucket(diff_atr: float, near: float = 0.25, material: float = 1.0) -> str:
    if abs(diff_atr) <= near:
        return "NEAR_IDENTICAL"
    if diff_atr > near:
        return "BETTER_5M"
    if diff_atr < -near:
        return "BETTER_1M"
    return "MATERIAL_DIFFERENCE" if abs(diff_atr) >= material else "NEAR_IDENTICAL"


def retention_tier(pct: float, high: float = 70, medium: float = 40) -> str:
    if pct >= high:
        return "HIGH"
    if pct >= medium:
        return "MEDIUM"
    return "LOW"


def _atr(arr: np.ndarray, i: int) -> float:
    v = arr[i] if i < len(arr) else np.nan
    if np.isfinite(v) and v > 0:
        return float(v)
    for k in range(max(0, i - 10), min(len(arr), i + 1)):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return float(arr[k])
    return 1.0
