"""Matched non-level controls for auction location interactions."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .location_config import MATCH_SEED, MATCH_TIME_BIN_MINUTES, MAX_SMD_ACCEPT


MATCH_COVARIATES = (
    "atr",
    "time_of_day_min",
    "range_5m",
    "range_15m",
    "range_30m",
    "disp_5m",
    "disp_15m",
    "disp_30m",
    "dist_from_session_open",
    "session_range_pct",
    "volume",
)


def _time_bin(minutes: float, bin_size: int = MATCH_TIME_BIN_MINUTES) -> int:
    if pd.isna(minutes):
        return -1
    return int(minutes // bin_size)


def _build_match_keys(df: pd.DataFrame) -> pd.Series:
    return (
        df["year"].astype(int).astype(str)
        + "_"
        + df["month"].astype(int).astype(str)
        + "_"
        + df["time_of_day_min"].apply(_time_bin).astype(str)
    )


def standardized_mean_diff(treated: pd.DataFrame, control: pd.DataFrame, col: str) -> float:
    a = treated[col].dropna().astype(float)
    b = control[col].dropna().astype(float)
    if len(a) < 2 or len(b) < 2:
        return np.nan
    pooled = np.sqrt((a.var(ddof=1) + b.var(ddof=1)) / 2.0)
    if pooled <= 0:
        return 0.0
    return float((a.mean() - b.mean()) / pooled)


def match_non_level_controls(
    auction_events: pd.DataFrame,
    pool: pd.DataFrame,
    *,
    seed: int = MATCH_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    Match each auction event to one non-level control bar.
    Returns (matched_pairs, control_events_with_paths_placeholder, match_diagnostics).
    """
    if auction_events.empty or pool.empty:
        return pd.DataFrame(), pd.DataFrame(), {"status": "EMPTY", "max_smd": np.nan}

    pool = pool.copy()
    pool["match_key"] = _build_match_keys(pool)
    auction = auction_events.copy()
    auction["match_key"] = _build_match_keys(auction)

    rng = np.random.RandomState(seed)
    pool_by_key: dict[str, list[int]] = {}
    for i, key in enumerate(pool["match_key"]):
        pool_by_key.setdefault(key, []).append(i)

    matched_control_idx: list[int] = []
    matched_treat_idx: list[int] = []
    for i, (_, row) in enumerate(auction.iterrows()):
        key = row["match_key"]
        candidates = pool_by_key.get(key, [])
        if not candidates:
            ym = f"{int(row['year'])}_{int(row['month'])}"
            candidates = [j for j, k in enumerate(pool["match_key"]) if str(k).startswith(ym)]
        if not candidates:
            continue
        ci = candidates[rng.randint(len(candidates))]
        matched_control_idx.append(ci)
        matched_treat_idx.append(i)

    if not matched_treat_idx:
        return pd.DataFrame(), pd.DataFrame(), {"status": "CONTROL_MATCH_FAIL", "max_smd": np.nan}

    treat = auction.iloc[matched_treat_idx].reset_index(drop=True)
    ctrl = pool.iloc[matched_control_idx].reset_index(drop=True)

    smds: dict[str, float] = {}
    for col in MATCH_COVARIATES:
        if col in treat.columns and col in ctrl.columns:
            smds[col] = standardized_mean_diff(treat, ctrl, col)
    max_smd = float(np.nanmax(list(smds.values()))) if smds else np.nan
    status = "ACCEPT" if (not np.isnan(max_smd) and max_smd <= MAX_SMD_ACCEPT) else "CONTROL_MATCH_FAIL"

    pairs = treat.copy()
    pairs["control_ts"] = ctrl["interaction_ts"].values
    for col in MATCH_COVARIATES:
        pairs[f"ctrl_{col}"] = ctrl[col].values

    diag = {
        "status": status,
        "max_smd": max_smd,
        "smd_by_covariate": smds,
        "n_matched": len(pairs),
        "n_requested": len(auction_events),
        "match_rate": len(pairs) / len(auction_events) if len(auction_events) else 0.0,
    }
    return pairs, ctrl, diag
