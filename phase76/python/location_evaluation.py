"""Location control evaluation, head-to-head, stability, practical effect gate."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .config import TRAIN_FRAC, VAL_FRAC
from .location_config import (
    HEAD_TO_HEAD,
    MIN_ABS_EXCURSION_LIFT_15,
    MIN_CLEAN_EXPANSION_LIFT,
    MIN_N_EVENTS,
    MIN_SIMPLE_SR_LIFT_FRACTION,
    MIN_SWEEP_DIFF,
    MIN_YEAR_FRACTION_SAME_SIGN,
    PRIMARY_BAND_ATR,
    PROFILE_VS_ROLLING,
    VAL_EFFECT_RATIO,
)


def chronological_splits(ts: pd.Series) -> pd.Series:
    """TRAIN 60% / VAL 20% / PREVIOUSLY_EXPOSED_HISTORICAL_TEST 20%."""
    order = ts.sort_values()
    n = len(order)
    t_end = int(n * TRAIN_FRAC)
    v_end = int(n * (TRAIN_FRAC + VAL_FRAC))
    split = pd.Series("PREVIOUSLY_EXPOSED_HISTORICAL_TEST", index=order.index)
    split.iloc[:t_end] = "TRAIN"
    split.iloc[t_end:v_end] = "VALIDATION"
    return split


def _lift(treat_mean: float, ctrl_mean: float) -> float:
    if np.isnan(treat_mean) or np.isnan(ctrl_mean):
        return np.nan
    return float(treat_mean - ctrl_mean)


def classify_location(
    *,
    match_status: str,
    n: int,
    train_lift_15: float,
    val_lift_15: float,
    clean_exp_lift: float,
    sweep_diff: float,
    beats_simple: bool,
    year_same_sign_frac: float,
    band_cliff: bool,
    level_category: str = "auction",
) -> str:
    if level_category == "simple":
        return "N/A_SIMPLE_BASELINE"
    if n < MIN_N_EVENTS:
        return "DATA_INSUFFICIENT"
    if match_status != "ACCEPT":
        return "CONTROL_MATCH_FAIL"
    if band_cliff:
        return "NO_LOCATION_INFORMATION"
    meaningful = (
        abs(train_lift_15) >= MIN_ABS_EXCURSION_LIFT_15
        or abs(clean_exp_lift) >= MIN_CLEAN_EXPANSION_LIFT
        or abs(sweep_diff) >= MIN_SWEEP_DIFF
    )
    if not meaningful:
        return "NO_LOCATION_INFORMATION"
    val_ok = (
        not np.isnan(val_lift_15)
        and not np.isnan(train_lift_15)
        and np.sign(val_lift_15) == np.sign(train_lift_15)
        and abs(val_lift_15) >= abs(train_lift_15) * VAL_EFFECT_RATIO
    )
    year_ok = year_same_sign_frac >= MIN_YEAR_FRACTION_SAME_SIGN
    if not val_ok or not year_ok or not beats_simple:
        return "WEAK_LOCATION_INFORMATION"
    if abs(train_lift_15) >= MIN_ABS_EXCURSION_LIFT_15 * 1.5 and val_ok and beats_simple and year_ok:
        return "MODERATE_LOCATION_INFORMATION"
    if abs(train_lift_15) >= MIN_ABS_EXCURSION_LIFT_15 * 2 and clean_exp_lift >= MIN_CLEAN_EXPANSION_LIFT:
        return "STRONG_LOCATION_INFORMATION"
    return "WEAK_LOCATION_INFORMATION"


def evaluate_level_vs_matched(
    treat_paths: pd.DataFrame,
    ctrl_paths: pd.DataFrame,
    match_diag: dict,
) -> dict[str, Any]:
    """Compare auction/simple level paths to matched non-level controls."""
    metric = "two_sided_range_15m"
    t_mean = treat_paths[metric].mean() if metric in treat_paths else np.nan
    c_mean = ctrl_paths[metric].mean() if metric in ctrl_paths else np.nan
    lift_15 = _lift(t_mean, c_mean)

    clean_t = treat_paths["clean_expansion"].mean() if "clean_expansion" in treat_paths else np.nan
    clean_c = ctrl_paths["clean_expansion"].mean() if "clean_expansion" in ctrl_paths else np.nan
    clean_lift = _lift(clean_t, clean_c)

    sweep_t = treat_paths["sweep_both_1.0"].mean() if "sweep_both_1.0" in treat_paths else np.nan
    sweep_c = ctrl_paths["sweep_both_1.0"].mean() if "sweep_both_1.0" in ctrl_paths else np.nan
    sweep_diff = _lift(sweep_t, sweep_c)

    splits_t = chronological_splits(treat_paths["interaction_ts"])
    treat_paths = treat_paths.copy()
    treat_paths["split"] = splits_t.values

    split_lifts: dict[str, float] = {}
    for name in ("TRAIN", "VALIDATION", "PREVIOUSLY_EXPOSED_HISTORICAL_TEST"):
        sub = treat_paths[treat_paths["split"] == name]
        if len(sub):
            split_lifts[name] = float(sub[metric].mean()) if metric in sub else np.nan

    train_lift = _lift(split_lifts.get("TRAIN", np.nan), c_mean)
    val_lift = _lift(split_lifts.get("VALIDATION", np.nan), c_mean)

    year_lifts: dict[int, float] = {}
    if "year" in treat_paths:
        for yr, grp in treat_paths.groupby("year"):
            year_lifts[int(yr)] = float(grp[metric].mean()) if len(grp) else np.nan
    base = c_mean
    same_sign = sum(1 for v in year_lifts.values() if not np.isnan(v) and (v - base) * train_lift >= 0)
    year_frac = same_sign / len(year_lifts) if year_lifts else 0.0

    return {
        "n": len(treat_paths),
        "match_status": match_diag.get("status"),
        "max_smd": match_diag.get("max_smd"),
        "two_sided_15_treat": float(t_mean) if not np.isnan(t_mean) else np.nan,
        "two_sided_15_control": float(c_mean) if not np.isnan(c_mean) else np.nan,
        "lift_two_sided_15": lift_15,
        "train_lift_15": train_lift,
        "val_lift_15": val_lift,
        "clean_expansion_treat": float(clean_t) if not np.isnan(clean_t) else np.nan,
        "clean_expansion_control": float(clean_c) if not np.isnan(clean_c) else np.nan,
        "clean_expansion_lift": clean_lift,
        "sweep_both_1_treat": float(sweep_t) if not np.isnan(sweep_t) else np.nan,
        "sweep_both_1_control": float(sweep_c) if not np.isnan(sweep_c) else np.nan,
        "sweep_diff": sweep_diff,
        "split_means": split_lifts,
        "year_means": year_lifts,
        "year_same_sign_frac": year_frac,
    }


def head_to_head_compare(
    paths_a: pd.DataFrame,
    paths_b: pd.DataFrame,
    *,
    label_a: str,
    label_b: str,
) -> dict[str, Any]:
    metric = "two_sided_range_15m"
    ma = paths_a[metric].mean() if not paths_a.empty and metric in paths_a else np.nan
    mb = paths_b[metric].mean() if not paths_b.empty and metric in paths_b else np.nan
    clean_a = paths_a["clean_expansion"].mean() if not paths_a.empty else np.nan
    clean_b = paths_b["clean_expansion"].mean() if not paths_b.empty else np.nan
    return {
        "level_a": label_a,
        "level_b": label_b,
        "n_a": len(paths_a),
        "n_b": len(paths_b),
        "two_sided_15_a": float(ma) if not np.isnan(ma) else np.nan,
        "two_sided_15_b": float(mb) if not np.isnan(mb) else np.nan,
        "lift_a_minus_b": _lift(ma, mb),
        "clean_exp_a": float(clean_a) if not np.isnan(clean_a) else np.nan,
        "clean_exp_b": float(clean_b) if not np.isnan(clean_b) else np.nan,
        "clean_lift_a_minus_b": _lift(clean_a, clean_b),
        "profile_beats_simple": bool(not np.isnan(ma) and not np.isnan(mb) and ma > mb),
    }


def detect_band_cliff(paths_by_band: dict[float, pd.DataFrame], metric: str = "two_sided_range_15m") -> bool:
    """True if effect jumps unrealistically between adjacent bands (tiny-band cliff)."""
    bands = sorted(paths_by_band.keys())
    if len(bands) < 2:
        return False
    means = [paths_by_band[b][metric].mean() if not paths_by_band[b].empty else np.nan for b in bands]
    for i in range(len(means) - 1):
        if np.isnan(means[i]) or np.isnan(means[i + 1]):
            continue
        if abs(means[i + 1] - means[i]) > MIN_ABS_EXCURSION_LIFT_15 * 3:
            return True
    return False


def final_phase76_verdict(level_results: list[dict], h2h_results: list[dict]) -> str:
    """
    Allowed conclusions per spec — conservative when matching fails or profile ≈ simple S/R.
    """
    primary_auction = [
        r for r in level_results
        if r.get("band_atr") == PRIMARY_BAND_ATR and r.get("level_category") == "auction"
    ]
    survivors = [
        r for r in primary_auction
        if r.get("verdict") in (
            "WEAK_LOCATION_INFORMATION",
            "MODERATE_LOCATION_INFORMATION",
            "STRONG_LOCATION_INFORMATION",
        )
    ]
    all_match_fail = all(r.get("verdict") == "CONTROL_MATCH_FAIL" for r in primary_auction)

    vah_beats_prior = _h2h_beats(h2h_results, "PRIOR_VAH", "PRIOR_SESSION_HIGH")
    val_beats_prior = _h2h_beats(h2h_results, "PRIOR_VAL", "PRIOR_SESSION_LOW")
    poc_beats_vwap = _h2h_beats(h2h_results, "DEV_POC", "VWAP") or _h2h_beats(h2h_results, "PRIOR_POC", "VWAP")
    profile_vs_simple_core = vah_beats_prior and val_beats_prior and poc_beats_vwap

    if not survivors:
        if all_match_fail:
            return "PHASE76_NO_AUCTION_INFORMATION"
        return "PHASE76_PROFILE_NOT_BETTER_THAN_SIMPLE_SR"

    if profile_vs_simple_core and any(
        r.get("verdict") in ("MODERATE_LOCATION_INFORMATION", "STRONG_LOCATION_INFORMATION") for r in survivors
    ):
        return "PHASE76_CONTEXT_FOLLOWUP_JUSTIFIED"

    if survivors:
        return "PHASE76_LOCATION_INFORMATION_ONLY"

    return "PHASE76_PROFILE_NOT_BETTER_THAN_SIMPLE_SR"


def _h2h_beats(h2h_results: list[dict], a: str, b: str) -> bool:
    for h in h2h_results:
        if h.get("level_a") == a and h.get("level_b") == b:
            return bool(h.get("profile_beats_simple"))
    return False


def summarize_level_result(
    level_type: str,
    category: str,
    band: float,
    eval_vs_matched: dict,
    *,
    beats_simple: bool,
    band_cliff: bool,
) -> dict[str, Any]:
    verdict = classify_location(
        match_status=eval_vs_matched.get("match_status", "CONTROL_MATCH_FAIL"),
        n=eval_vs_matched.get("n", 0),
        train_lift_15=eval_vs_matched.get("train_lift_15", np.nan),
        val_lift_15=eval_vs_matched.get("val_lift_15", np.nan),
        clean_exp_lift=eval_vs_matched.get("clean_expansion_lift", np.nan),
        sweep_diff=eval_vs_matched.get("sweep_diff", np.nan),
        beats_simple=beats_simple,
        year_same_sign_frac=eval_vs_matched.get("year_same_sign_frac", 0.0),
        band_cliff=band_cliff,
        level_category=category,
    )
    return {
        "level_type": level_type,
        "level_category": category,
        "band_atr": band,
        **eval_vs_matched,
        "beats_simple_sr": beats_simple,
        "band_cliff": band_cliff,
        "verdict": verdict,
    }
