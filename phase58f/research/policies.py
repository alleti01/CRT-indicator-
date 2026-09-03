"""Abstention policies P0–P4."""
from __future__ import annotations

import pandas as pd


def apply_policy(df: pd.DataFrame, policy: str) -> pd.Series:
    """Return KEEP/ABSTAIN for each trade."""
    band = df["direction_confidence_band"]
    fr = df["false_reversal_risk"]
    rev = df["reversal_support"]

    if policy == "P0":
        return pd.Series(["KEEP"] * len(df), index=df.index)

    if policy == "P1":
        return band.apply(lambda b: "ABSTAIN" if b == "VERY_LOW" else "KEEP")

    if policy == "P2":
        return band.apply(lambda b: "ABSTAIN" if b in ("LOW", "VERY_LOW") else "KEEP")

    if policy == "P3":
        return pd.Series([
            "ABSTAIN" if b in ("LOW", "VERY_LOW") and f == "HIGH" else "KEEP"
            for b, f in zip(band, fr)
        ], index=df.index)

    if policy == "P4":
        def _p4(row):
            strong_contra = (
                (row["original_direction"] == "LONG" and row["15m_state"] == "BEARISH" and row.get("dominant_active") in ("DOWN", "STRONG_DOWN"))
                or (row["original_direction"] == "SHORT" and row["15m_state"] == "BULLISH" and row.get("dominant_active") in ("UP", "STRONG_UP"))
            )
            weak_rev = row["reversal_support"] in ("NONE", "WEAK")
            return "ABSTAIN" if strong_contra and weak_rev else "KEEP"
        return df.apply(_p4, axis=1)

    return pd.Series(["KEEP"] * len(df), index=df.index)
