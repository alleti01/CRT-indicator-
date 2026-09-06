"""Randomized direction control gate — full methodology Families A–F."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from .config import CHECKPOINTS, REPORTS, TRAIN_FRAC, VAL_FRAC
from .path_engine import (
    aggregate_metrics,
    distribution_stats,
    evaluate_randomized_directions,
    metrics_for_direction,
    precompute_signal_paths,
)
from .path_audit import FP_PAIRS, HORIZONS
from .randomized_gate import (
    INVERSE_MARGIN_FP21,
    MIN_EFFECT_FP11,
    MIN_EFFECT_FP21,
    MIN_N_FAMILY,
    MIN_PERCENTILE_STRONG,
    MIN_PERCENTILE_WEAK,
    RANDOM_SEED_COUNT,
    RANDOM_SEED_START,
    STRONG_ASYM_15,
    TIMESTAMP_SHIFT_BARS,
    WEAK_ASYM_15,
)

KEY_FP11 = "fp_1.0atr_before_1.0atr"
KEY_FP21 = "fp_2.0atr_before_1.0atr"
KEY_FP251 = "fp_2.5atr_before_1.0atr"


@dataclass
class FamilySpec:
    code: str
    name: str
    generator: Callable[[pd.DataFrame], pd.DataFrame]


def assign_chronological_split(signal_ts: pd.Series) -> pd.Series:
    ts = pd.to_datetime(signal_ts)
    order = ts.sort_values()
    n = len(order)
    t_cut = int(n * TRAIN_FRAC)
    v_cut = int(n * (TRAIN_FRAC + VAL_FRAC))
    rank = pd.Series(index=signal_ts.index, dtype=object)
    sorted_idx = order.index
    for i, idx in enumerate(sorted_idx):
        if i < t_cut:
            rank[idx] = "TRAIN"
        elif i < v_cut:
            rank[idx] = "VALIDATION"
        else:
            rank[idx] = "PREVIOUSLY_EXPOSED_HISTORICAL_TEST"
    return rank


def _real_metrics(precomputed: pd.DataFrame) -> dict[str, float]:
    """Vectorized real-direction metrics from dual-path columns."""
    if precomputed.empty:
        return {"n": 0}
    n = len(precomputed)
    is_long = (precomputed["direction"].values == "LONG")
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
    out["n_long"] = int(is_long.sum())
    out["n_short"] = int(n - is_long.sum())
    return out


def _flip_metrics(precomputed: pd.DataFrame) -> dict[str, float]:
    if precomputed.empty:
        return {"n": 0}
    flip_dirs = precomputed["direction"].map({"LONG": "SHORT", "SHORT": "LONG"})
    tmp = precomputed.copy()
    tmp["direction"] = flip_dirs
    return _real_metrics(tmp)


def _shift_metrics(precomputed: pd.DataFrame, ohlc: pd.DataFrame, shift_bars: int) -> dict[str, float]:
    """Placebo: same direction, entry shifted forward by N bars (causal)."""
    from .path_engine import compute_dual_paths

    if precomputed.empty:
        return {"n": 0}
    highs = ohlc["high"].values
    lows = ohlc["low"].values
    opens = ohlc["open"].values
    rows = []
    for i in range(len(precomputed)):
        row = precomputed.iloc[i]
        eidx = int(row["entry_idx"]) + shift_bars
        if eidx >= len(opens):
            continue
        atr = row["atr_used"]
        if np.isnan(atr) or atr <= 0:
            continue
        entry_px = float(opens[eidx])
        paths = compute_dual_paths(eidx, entry_px, float(atr), highs, lows)
        if not paths:
            continue
        rec = row.to_dict()
        rec.update(paths)
        rec["entry_price"] = entry_px
        rec["entry_idx"] = eidx
        rows.append(rec)
    if not rows:
        return {"n": 0}
    return _real_metrics(pd.DataFrame(rows))


def compute_all_random_seed_metrics(precomputed: pd.DataFrame) -> list[dict[str, float]]:
    """Run all preregistered seeds once — reuse for every metric distribution."""
    return [
        evaluate_randomized_directions(precomputed, precomputed["direction"], s)
        for s in range(RANDOM_SEED_START, RANDOM_SEED_START + RANDOM_SEED_COUNT)
    ]


def _metric_from_seeds(seed_metrics: list[dict[str, float]], metric_key: str) -> list[float]:
    return [m.get(metric_key, np.nan) for m in seed_metrics]


def _random_distribution(precomputed: pd.DataFrame, metric_key: str, seed_metrics: list[dict[str, float]] | None = None) -> list[float]:
    if seed_metrics is not None:
        return _metric_from_seeds(seed_metrics, metric_key)
    return _metric_from_seeds(compute_all_random_seed_metrics(precomputed), metric_key)


def classify_verdict(
    real: dict[str, float],
    flip: dict[str, float],
    fp11_stats: dict[str, float],
    fp21_stats: dict[str, float],
) -> str:
    n = real.get("n", 0)
    if n < MIN_N_FAMILY:
        return "DATA_INSUFFICIENT"

    real_fp11 = real.get(KEY_FP11, np.nan)
    real_fp21 = real.get(KEY_FP21, np.nan)
    flip_fp21 = flip.get(KEY_FP21, np.nan)
    asym_15 = real.get("asym_15m", np.nan)

    if not np.isnan(flip_fp21) and not np.isnan(real_fp21):
        if flip_fp21 - real_fp21 >= INVERSE_MARGIN_FP21:
            return "INVERSE_INFORMATION"

    strong = (
        fp11_stats.get("real_minus_mean", -999) >= MIN_EFFECT_FP11
        and fp21_stats.get("real_minus_mean", -999) >= MIN_EFFECT_FP21
        and fp11_stats.get("real_percentile", 0) >= MIN_PERCENTILE_STRONG
        and fp21_stats.get("real_percentile", 0) >= MIN_PERCENTILE_STRONG
        and asym_15 >= STRONG_ASYM_15
    )
    if strong:
        return "STRONG_DIRECTIONAL_INFORMATION"

    weak = (
        fp11_stats.get("real_minus_mean", -999) >= MIN_EFFECT_FP11 * 0.5
        and fp21_stats.get("real_percentile", 0) >= MIN_PERCENTILE_WEAK
        and asym_15 >= WEAK_ASYM_15
    )
    if weak:
        return "WEAK_DIRECTIONAL_INFORMATION"

    return "NO_DIRECTIONAL_INFORMATION"


def run_family_gate(
    spec: FamilySpec,
    precomputed: pd.DataFrame,
    ohlc: pd.DataFrame,
) -> dict[str, Any]:
    if precomputed.empty:
        return {
            "family": spec.code,
            "name": spec.name,
            "n": 0,
            "verdict": "DATA_INSUFFICIENT",
            "reason": "no signals",
        }

    real = _real_metrics(precomputed)
    flip = _flip_metrics(precomputed)

    seed_metrics = compute_all_random_seed_metrics(precomputed)

    fp11_rand = _random_distribution(precomputed, KEY_FP11, seed_metrics)
    fp21_rand = _random_distribution(precomputed, KEY_FP21, seed_metrics)

    fp11_stats = distribution_stats(real.get(KEY_FP11, np.nan), fp11_rand)
    fp21_stats = distribution_stats(real.get(KEY_FP21, np.nan), fp21_rand)

    verdict = classify_verdict(real, flip, fp11_stats, fp21_stats)

    # Side breakdown
    sides = {}
    for side in ("LONG", "SHORT"):
        sub = precomputed[precomputed["direction"] == side]
        if len(sub) >= 50:
            sides[side] = _real_metrics(sub)

    # Chronological splits
    precomputed = precomputed.copy()
    precomputed["split"] = assign_chronological_split(precomputed["signal_ts"])
    splits = {}
    for split_name in ("TRAIN", "VALIDATION", "PREVIOUSLY_EXPOSED_HISTORICAL_TEST"):
        sub = precomputed[precomputed["split"] == split_name]
        if len(sub) >= 50:
            splits[split_name] = _real_metrics(sub)

    # Year breakdown
    years = {}
    ts_et = pd.to_datetime(precomputed["signal_ts"])
    if ts_et.dt.tz is None:
        ts_et = ts_et.dt.tz_localize("UTC")
    precomputed["year"] = ts_et.dt.tz_convert("America/New_York").dt.year
    for yr, grp in precomputed.groupby("year"):
        if len(grp) < 50:
            continue
        years[int(yr)] = _real_metrics(grp)

    # Timestamp shift placebos (vectorized; 3 preregistered shifts)
    shifts = {}
    for sb in TIMESTAMP_SHIFT_BARS:
        shifts[f"shift_{sb}bars"] = _shift_metrics(precomputed, ohlc, sb)

    # Metric detail table
    metrics_detail = []
    for key in [KEY_FP11, KEY_FP21, KEY_FP251, "asym_15m", "asym_60m"]:
        rand_vals = _random_distribution(precomputed, key, seed_metrics)
        real_val = real.get(key, np.nan)
        stats = distribution_stats(real_val, rand_vals) if rand_vals else {}
        metrics_detail.append({"metric": key, **stats})

    return {
        "family": spec.code,
        "name": spec.name,
        "n": int(real.get("n", 0)),
        "verdict": verdict,
        "real": real,
        "flip": flip,
        "fp11_stats": fp11_stats,
        "fp21_stats": fp21_stats,
        "metrics_detail": metrics_detail,
        "sides": sides,
        "splits": splits,
        "years": years,
        "shifts": shifts,
        "passes_random_gate": verdict in ("STRONG_DIRECTIONAL_INFORMATION", "WEAK_DIRECTIONAL_INFORMATION"),
    }


def summary_row(result: dict[str, Any]) -> dict[str, Any]:
    real = result.get("real", {})
    fp21 = result.get("fp21_stats", {})
    fp11 = result.get("fp11_stats", {})
    flip = result.get("flip", {})
    splits = result.get("splits", {})
    rand_fp21_mean = fp21.get("rand_mean", np.nan)
    return {
        "family": result["family"],
        "n": result.get("n", 0),
        "real_fp11": real.get(KEY_FP11, np.nan),
        "rand_fp11_mean": fp11.get("rand_mean", np.nan),
        "real_fp21": real.get(KEY_FP21, np.nan),
        "rand_fp21_mean": rand_fp21_mean,
        "real_asym_15": real.get("asym_15m", np.nan),
        "rand_asym_15_proxy": np.nan,
        "flip_fp21": flip.get(KEY_FP21, np.nan),
        "train_fp21": splits.get("TRAIN", {}).get(KEY_FP21, np.nan),
        "val_fp21": splits.get("VALIDATION", {}).get(KEY_FP21, np.nan),
        "hist_test_fp21": splits.get("PREVIOUSLY_EXPOSED_HISTORICAL_TEST", {}).get(KEY_FP21, np.nan),
        "verdict": result.get("verdict", ""),
        "passes_gate": result.get("passes_random_gate", False),
    }
