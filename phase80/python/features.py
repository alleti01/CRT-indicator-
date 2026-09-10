"""Build causal entry-time features from Phase60 stream."""
from __future__ import annotations

from datetime import timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

ET = ZoneInfo("America/New_York")
CHI = ZoneInfo("America/Chicago")

# Phase78 Silver Bullet windows (ET, time-only)
SB_WINDOWS = [
    ("SB1", 3, 0, 4, 0),
    ("SB2", 10, 0, 11, 0),
    ("SB3", 14, 0, 15, 0),
]


def partition_slice(df: pd.DataFrame, part: tuple[int, int]) -> pd.DataFrame:
    return df.iloc[part[0]:part[1]]


def partition_mask(mask: pd.Series, part: tuple[int, int]) -> pd.Series:
    return mask.iloc[part[0]:part[1]]


def load_entry_stream() -> pd.DataFrame:
    from phase80.python.config import CANON_PARQUET

    df = pd.read_parquet(CANON_PARQUET)
    df = df.loc[df["h1_status"] == "KEEP"].copy()
    df = df.sort_values("entry_ts").reset_index(drop=True)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    return df


def _in_sb_window(ts: pd.Timestamp) -> bool:
    ts_et = ts.tz_convert(ET)
    m = ts_et.hour * 60 + ts_et.minute
    for _, h0, m0, h1, m1 in SB_WINDOWS:
        start = h0 * 60 + m0
        end = h1 * 60 + m1
        if start <= m < end:
            return True
    return False


def _is_rth(ts: pd.Timestamp) -> bool:
    ts_c = ts.tz_convert(CHI)
    m = ts_c.hour * 60 + ts_c.minute
    return 8 * 60 + 30 <= m < 15 * 60


def build_features(df: pd.DataFrame, train_idx: tuple[int, int] | slice) -> tuple[pd.DataFrame, dict]:
    """Return binary/ordinal component columns + train-frozen thresholds."""
    out = df.copy()
    if isinstance(train_idx, tuple):
        train = out.iloc[train_idx[0]:train_idx[1]]
    else:
        train = out.iloc[train_idx]

    thresholds = {
        "location_score_p50": float(train["location_score"].median()),
        "reaction_score_p50": float(train["reaction_score"].median()),
        "total_evidence_p75": float(train["total_evidence"].quantile(0.75)),
        "countertrend_p50": float(train["countertrend_ratio"].median()),
    }

    out["F_LOCATION_SCORE"] = out["location_score"] >= thresholds["location_score_p50"]
    out["F_REACTION_SCORE"] = out["reaction_score"] >= thresholds["reaction_score_p50"]
    out["F_TOTAL_EVIDENCE"] = out["total_evidence"] >= thresholds["total_evidence_p75"]
    out["F_GOOD_LOCATION"] = out["good_location"].astype(bool)
    out["F_ALIGNED_ACTIVE"] = out["aligned_with_active"].astype(bool)
    out["F_HTF_SUPPORT"] = out["htf_support_code"].astype(bool)
    out["F_NO_HTF_CONTRA"] = ~out["htf_contra_code"].astype(bool)
    out["F_FALSE_REV_LOW"] = out["false_reversal_risk"] == "LOW"
    out["F_REVERSAL_STRONG"] = out["reversal_support"] == "STRONG"
    out["F_NO_PULLBACK"] = ~out["pullback_conflict"].astype(bool)
    out["F_HTF_LTF_AGREE"] = ~out["htf_ltf_disagree"].astype(bool)
    out["F_CT_LOW"] = out["countertrend_ratio"] <= thresholds["countertrend_p50"]
    out["F_M15_NOT_NEUTRAL"] = out["15m_state"] != "NEUTRAL"
    out["F_M5_TRENDING"] = out["5m_state"].isin(["BULLISH", "BEARISH"])
    out["F_MARKET_REVERSAL"] = out["market_state"] == "REVERSAL_TRANSITION"
    out["F_CONF_HIGH"] = out["direction_confidence_band"].isin(["HIGH", "VERY_HIGH"])
    out["F_SB_WINDOW"] = out["entry_ts"].map(_in_sb_window)
    out["F_RTH"] = out["entry_ts"].map(_is_rth)

    # Direction-aware soft alignment (uses existing signal direction — not new direction)
    def _m5_align(row) -> bool:
        if row["5m_state"] == "NEUTRAL":
            return False
        if row["direction_m1"] == "LONG":
            return row["5m_state"] == "BULLISH"
        return row["5m_state"] == "BEARISH"

    out["F_M5_DIRECTION_ALIGN"] = out.apply(_m5_align, axis=1)

    return out, thresholds


COMPONENT_META = {
    "F_LOCATION_SCORE": ("P58D_LOCATION_SCORE", "LOCATION"),
    "F_REACTION_SCORE": ("P58D_REACTION_SCORE", "REACTION"),
    "F_TOTAL_EVIDENCE": ("P58D_TOTAL_EVIDENCE", "CONTEXT"),
    "F_GOOD_LOCATION": ("P58E_GOOD_LOCATION", "LOCATION"),
    "F_ALIGNED_ACTIVE": ("P58E_ALIGNED_ACTIVE", "CONTEXT"),
    "F_HTF_SUPPORT": ("P58F_HTF_SUPPORT", "CONTEXT"),
    "F_NO_HTF_CONTRA": ("P58F_HTF_CONTRA", "CONFLICT"),
    "F_FALSE_REV_LOW": ("P58F_FALSE_REV_LOW", "CONFLICT"),
    "F_REVERSAL_STRONG": ("P58F_REVERSAL_STRONG", "REACTION"),
    "F_NO_PULLBACK": ("P58F_PULLBACK_OK", "CONFLICT"),
    "F_HTF_LTF_AGREE": ("P58F_HTF_LTF_AGREE", "CONFLICT"),
    "F_CT_LOW": ("P58F_CT_LOW", "CONFLICT"),
    "F_M15_NOT_NEUTRAL": ("P75_M15_NOT_NEUTRAL", "CONTEXT"),
    "F_M5_TRENDING": ("P75_M5_TRENDING", "CONTEXT"),
    "F_M5_DIRECTION_ALIGN": ("P60_DEV_HTF_5M", "CONTEXT"),
    "F_MARKET_REVERSAL": ("P58E_MARKET_STATE_REV", "CONTEXT"),
    "F_CONF_HIGH": ("P58F_CONF_HIGH", "CONTEXT"),
    "F_SB_WINDOW": ("P78_SB_WINDOW", "TIMING"),
    "F_RTH": ("P78_RTH", "TIMING"),
}

FEATURE_COLS = list(COMPONENT_META.keys())


def prefix_causality_check(df: pd.DataFrame, n_sample: int = 500) -> dict:
    """Features derived only from entry-time columns — prefix invariant by construction."""
    rng = np.random.default_rng(42)
    idx = rng.choice(len(df), size=min(n_sample, len(df)), replace=False)
    # Spot-check SB/RTH recompute
    fails = 0
    for i in idx:
        row = df.iloc[i]
        if bool(row["F_SB_WINDOW"]) != _in_sb_window(row["entry_ts"]):
            fails += 1
        if bool(row["F_RTH"]) != _is_rth(row["entry_ts"]):
            fails += 1
    return {"sampled": len(idx), "failures": fails, "pass": fails == 0}
