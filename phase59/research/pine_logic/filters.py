"""Phase58H surgical conflict filter models H0-H4."""
from __future__ import annotations

import pandas as pd

from phase58f.research.policies import apply_policy


def h1_mask(df: pd.DataFrame) -> pd.Series:
    return (df["high_subtype"] == "HIGH_CONFLICTED") & df["htf_contra_code"]


def h2_mask(df: pd.DataFrame) -> pd.Series:
    return h1_mask(df) & df["reversal_support"].isin(["NONE", "WEAK"])


def h3_mask(df: pd.DataFrame) -> pd.Series:
    return h2_mask(df) & ~df["good_location"]


def h4_mask(df: pd.DataFrame) -> pd.Series:
    strong_opp = (
        ((df["original_direction"] == "LONG") & (df["dominant_active"] == "STRONG_DOWN"))
        | ((df["original_direction"] == "SHORT") & (df["dominant_active"] == "STRONG_UP"))
    )
    return h2_mask(df) & strong_opp


def apply_h_model(df: pd.DataFrame, model: str) -> pd.Series:
    """Return KEEP/ABSTAIN. H0 = P4 only; H1-H4 stack surgical filter on P4."""
    p4_abstain = apply_policy(df, "P4") == "ABSTAIN"

    if model == "H0":
        surgical = pd.Series(False, index=df.index)
    elif model == "H1":
        surgical = h1_mask(df)
    elif model == "H2":
        surgical = h2_mask(df)
    elif model == "H3":
        surgical = h3_mask(df)
    elif model == "H4":
        surgical = h4_mask(df)
    else:
        raise ValueError(f"Unknown model {model}")

    abstain = p4_abstain | surgical
    return abstain.map({True: "ABSTAIN", False: "KEEP"})
