"""Fast path metrics at fixed entry — LONG/SHORT precomputed per signal."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .path_audit import FP_PAIRS, HORIZONS


def _first_passage(highs, lows, entry: float, atr: float, tg: float, st: float, direction: str) -> float:
    hit_tg = hit_st = False
    for hi, lo in zip(highs, lows):
        if direction == "LONG":
            if (hi - entry) / atr >= tg:
                hit_tg = True
            if (entry - lo) / atr >= st:
                hit_st = True
        else:
            if (entry - lo) / atr >= tg:
                hit_tg = True
            if (hi - entry) / atr >= st:
                hit_st = True
        if hit_tg and not hit_st:
            return 1.0
        if hit_st and not hit_tg:
            return 0.0
    if hit_tg and hit_st:
        return 0.5
    return np.nan


def compute_dual_paths(
    entry_idx: int,
    entry_price: float,
    atr: float,
    highs: np.ndarray,
    lows: np.ndarray,
    max_bars: int = 60,
) -> dict[str, float]:
    """Return path metrics for LONG and SHORT at fixed entry."""
    end = min(entry_idx + max_bars, len(highs))
    h = highs[entry_idx:end]
    l = lows[entry_idx:end]
    if len(h) == 0 or atr <= 0 or np.isnan(atr):
        return {}
    out: dict[str, float] = {}
    for direction in ("LONG", "SHORT"):
        prefix = direction[0]  # L or S — use full name in keys
        for horizon in HORIZONS:
            w = min(horizon, len(h))
            hh, ll = h[:w], l[:w]
            if direction == "LONG":
                out[f"mfe_{horizon}m_{direction}"] = (hh.max() - entry_price) / atr
                out[f"mae_{horizon}m_{direction}"] = (entry_price - ll.min()) / atr
            else:
                out[f"mfe_{horizon}m_{direction}"] = (entry_price - ll.min()) / atr
                out[f"mae_{horizon}m_{direction}"] = (hh.max() - entry_price) / atr
        for tg, st in FP_PAIRS:
            key = f"fp_{tg}atr_before_{st}atr_{direction}"
            out[key] = _first_passage(h, l, entry_price, atr, tg, st, direction)
    return out


def precompute_signal_paths(signals: pd.DataFrame, ohlc: pd.DataFrame) -> pd.DataFrame:
    """Attach LONG/SHORT path columns for frozen entry_ts / entry_price."""
    if signals.empty:
        return signals
    idx = ohlc.index
    highs = ohlc["high"].values
    lows = ohlc["low"].values
    rows = []
    for _, row in signals.iterrows():
        if pd.isna(row.get("entry_ts")):
            continue
        try:
            eidx = idx.get_loc(row["entry_ts"])
        except KeyError:
            continue
        atr = row.get("atr")
        if pd.isna(atr):
            atr = ohlc.iloc[eidx - 1]["atr"] if eidx > 0 else np.nan
        if pd.isna(atr) or atr <= 0:
            continue
        paths = compute_dual_paths(int(eidx), float(row["entry_price"]), float(atr), highs, lows)
        if not paths:
            continue
        rec = row.to_dict()
        rec.update(paths)
        rec["entry_idx"] = int(eidx)
        rec["atr_used"] = float(atr)
        rows.append(rec)
    return pd.DataFrame(rows)


def metrics_for_direction(precomputed: pd.DataFrame, direction: str) -> pd.DataFrame:
    """Select metrics for prescribed direction from dual-path columns."""
    if precomputed.empty:
        return precomputed
    out = precomputed.copy()
    out["direction_eval"] = direction
    for h in HORIZONS:
        out[f"mfe_{h}m"] = precomputed[f"mfe_{h}m_{direction}"]
        out[f"mae_{h}m"] = precomputed[f"mae_{h}m_{direction}"]
    for tg, st in FP_PAIRS:
        out[f"fp_{tg}atr_before_{st}atr"] = precomputed[f"fp_{tg}atr_before_{st}atr_{direction}"]
    return out


def aggregate_metrics(df: pd.DataFrame) -> dict[str, float]:
    """Mean metrics across signals."""
    if df.empty:
        return {"n": 0}
    out: dict[str, float] = {"n": len(df)}
    for h in HORIZONS:
        mfe = df[f"mfe_{h}m"].dropna()
        mae = df[f"mae_{h}m"].dropna()
        if len(mfe):
            out[f"mfe_{h}m"] = float(mfe.mean())
            out[f"mae_{h}m"] = float(mae.mean())
            if mae.mean():
                out[f"asym_{h}m"] = float(mfe.mean() / mae.mean())
    for tg, st in FP_PAIRS:
        col = f"fp_{tg}atr_before_{st}atr"
        s = df[col].dropna()
        if len(s):
            out[col] = float(s.mean())
    long_n = (df["direction_eval"] == "LONG").sum() if "direction_eval" in df else 0
    short_n = (df["direction_eval"] == "SHORT").sum() if "direction_eval" in df else 0
    out["n_long"] = int(long_n)
    out["n_short"] = int(short_n)
    return out


def random_directions(n: int, seed: int) -> np.ndarray:
    rng = np.random.RandomState(seed)
    return np.where(rng.rand(n) < 0.5, "LONG", "SHORT")


def evaluate_randomized_directions(precomputed: pd.DataFrame, real_directions: pd.Series, seed: int) -> dict[str, float]:
    """One random-direction seed — pick LONG or SHORT path per signal."""
    n = len(precomputed)
    is_long = random_directions(n, seed) == "LONG"
    out: dict[str, float] = {"n": n}
    for h in HORIZONS:
        mfe = np.where(is_long, precomputed[f"mfe_{h}m_LONG"].values, precomputed[f"mfe_{h}m_SHORT"].values)
        mae = np.where(is_long, precomputed[f"mae_{h}m_LONG"].values, precomputed[f"mae_{h}m_SHORT"].values)
        mfe = mfe[~np.isnan(mfe)]
        mae = mae[~np.isnan(mae)]
        if len(mfe):
            out[f"mfe_{h}m"] = float(mfe.mean())
            out[f"mae_{h}m"] = float(mae.mean())
            if mae.mean():
                out[f"asym_{h}m"] = float(mfe.mean() / mae.mean())
    for tg, st in FP_PAIRS:
        col = f"fp_{tg}atr_before_{st}atr"
        vals = np.where(
            is_long,
            precomputed[f"{col}_LONG"].values,
            precomputed[f"{col}_SHORT"].values,
        )
        vals = vals[~np.isnan(vals)]
        if len(vals):
            out[col] = float(vals.mean())
    return out


def distribution_stats(real_value: float, random_values: list[float]) -> dict[str, float]:
    arr = np.array(random_values, dtype=float)
    if len(arr) == 0 or np.isnan(real_value):
        return {}
    return {
        "real": real_value,
        "rand_mean": float(np.mean(arr)),
        "rand_median": float(np.median(arr)),
        "rand_std": float(np.std(arr)),
        "rand_p5": float(np.percentile(arr, 5)),
        "rand_p95": float(np.percentile(arr, 95)),
        "real_percentile": float((arr < real_value).mean() * 100),
        "real_minus_mean": float(real_value - np.mean(arr)),
    }
