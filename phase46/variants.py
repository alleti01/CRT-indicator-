"""VWAP filter variants V1–V5."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import load_market_1m
from phase45.execution.simulate import simulate_1m

from .config import B0_WINDOW_MIN, V3_SLOPE_WINDOWS, V4_MAX_DIST_ATR, V5_TOL_ATR, V5_WAIT_BARS
from .vwap import attach_session_vwap, vwap_retest_entry


def _dir_long(direction: str) -> bool:
    return str(direction).lower() == "long"


def pass_v1_side(row: pd.Series) -> bool:
    if not row.get("b0_filled", row.get("B0_filled", False)):
        return False
    vwap = row.get("vwap_at_confirm", np.nan)
    entry = row.get("B0_entry_price", np.nan)
    if not np.isfinite(vwap) or not np.isfinite(entry):
        return False
    if _dir_long(row["direction"]):
        return entry > vwap
    return entry < vwap


def pass_v2_reclaim(row: pd.Series) -> bool:
    if not row.get("b0_filled", row.get("B0_filled", False)):
        return False
    return bool(row.get("reclaim_vwap", False))


def pass_v3_slope(row: pd.Series, slope_col: str) -> bool:
    if not row.get("b0_filled", row.get("B0_filled", False)):
        return False
    slope = row.get(slope_col, np.nan)
    if not np.isfinite(slope):
        return False
    if _dir_long(row["direction"]):
        return slope > 0
    return slope < 0


def pass_v4_distance(row: pd.Series, max_atr: float | None) -> bool:
    if not row.get("b0_filled", row.get("B0_filled", False)):
        return False
    dist = row.get("abs_vwap_dist_atr", np.nan)
    if not np.isfinite(dist):
        return False
    if max_atr is None:
        return True
    return dist <= max_atr


def apply_v5_retest(trades: pd.DataFrame, market: pd.DataFrame, tol_atr: float, max_wait: int) -> pd.DataFrame:
    """V5: optional delayed entry after B1 via VWAP retest."""
    out = trades.copy()
    prefix = f"V5_t{tol_atr}_w{max_wait}"
    out[f"{prefix}_filled"] = False
    out[f"{prefix}_net_R"] = np.nan
    out[f"{prefix}_entry_price"] = np.nan
    out[f"{prefix}_delay_min"] = np.nan
    out[f"{prefix}_MFE_R"] = np.nan
    out[f"{prefix}_MAE_R"] = np.nan
    out[f"{prefix}_wrong_direction"] = np.nan
    for idx, row in out.iterrows():
        if not row.get("b0_filled", row.get("B0_filled", False)):
            continue
        entry_i = int(row.get("entry_i", -1))
        if entry_i < 0:
            continue
        ok, j, px = vwap_retest_entry(market, entry_i, row["direction"], tol_atr=tol_atr, max_wait=max_wait)
        if not ok:
            continue
        sim = simulate_1m(
            market,
            j,
            px,
            float(row["stop"]),
            float(row["target"]),
            row["direction"],
            row["signal_type"],
        )
        out.at[idx, f"{prefix}_filled"] = True
        out.at[idx, f"{prefix}_net_R"] = sim["net_R"]
        out.at[idx, f"{prefix}_entry_price"] = px
        base_delay = float(row.get("B0_delay_min", 0))
        out.at[idx, f"{prefix}_delay_min"] = base_delay + (j - entry_i)
        out.at[idx, f"{prefix}_MFE_R"] = sim["MFE_R"]
        out.at[idx, f"{prefix}_MAE_R"] = sim["MAE_R"]
        out.at[idx, f"{prefix}_wrong_direction"] = sim["wrong_direction"]
    return out


def apply_variant_mask(trades: pd.DataFrame, variant: str, **params) -> pd.Series:
    if variant == "V1":
        return trades.apply(pass_v1_side, axis=1)
    if variant == "V2":
        return trades.apply(pass_v2_reclaim, axis=1)
    if variant == "V3":
        col = params.get("slope_col", "vwap_slope_3")
        return trades.apply(lambda r: pass_v3_slope(r, col), axis=1)
    if variant == "V4":
        return trades.apply(lambda r: pass_v4_distance(r, params.get("max_atr")), axis=1)
    raise ValueError(variant)
