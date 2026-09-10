"""Short model architectures S0-S14."""
from __future__ import annotations

import pandas as pd


def apply_short_model(model_id: str, feat: pd.DataFrame, train_feat: pd.DataFrame) -> pd.Series:
    """Return boolean mask over feat rows (indexed by trade_id alignment)."""
    rs_med = float(train_feat["reaction_score"].median())
    ls_med = float(train_feat["location_score"].median())

    f = feat
    if model_id == "S0":
        return pd.Series(True, index=f.index)
    if model_id == "S1":
        return (
            f["good_location"]
            & f["false_rev_low"]
            & f["reversal_strong"]
            & (f["reaction_score"] >= rs_med)
            & (f["m5_bearish"] | f["m15_bearish"])
            & f["bearish_bar"]
        )
    if model_id == "S2":
        return f["breakdown_10"] & f["displacement"] & f["bearish_bar"]
    if model_id == "S3":
        return f["bounce_fail"] & f["bearish_bar"] & (f["reaction_score"] >= rs_med)
    if model_id == "S4":
        return (~f["aligned_active"]) & f["m5_bearish"] & f["false_rev_low"] & f["displacement"]
    if model_id == "S5":
        return f["failed_reclaim"] & f["bearish_bar"]
    if model_id == "S6":
        return f["micro_bos_8"] & f["bearish_bar"]
    if model_id == "S7":
        return f["displacement"] & (f["body_atr"] >= 0.5)
    if model_id == "S8":
        return ~f["late_chase"]
    if model_id == "S9":
        return ~f["htf_contra"] & ~f["pullback_conflict"]
    if model_id == "S10":
        return apply_short_model("S1", f, train_feat) | apply_short_model("S2", f, train_feat)
    if model_id == "S11":
        return apply_short_model("S1", f, train_feat) | apply_short_model("S3", f, train_feat)
    if model_id == "S12":
        return apply_short_model("S2", f, train_feat) | apply_short_model("S3", f, train_feat)
    if model_id == "S13":
        return (
            apply_short_model("S1", f, train_feat)
            | apply_short_model("S2", f, train_feat)
            | apply_short_model("S3", f, train_feat)
        )
    if model_id == "S14":
        loc = f["good_location"] | (f["location_score"] >= ls_med)
        react = (f["reaction_score"] >= rs_med) | f["displacement"]
        conflict = ~f["htf_contra"] & ~f["pullback_conflict"]
        return loc & react & conflict & f["bearish_bar"]
    raise KeyError(model_id)


MODEL_IDS = [
    "S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9",
    "S10", "S11", "S12", "S13", "S14",
]
