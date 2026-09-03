"""Build frozen Phase 40 signal population with outcome labels."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase39.classify import classify_dataframe
from phase39.config import (
    CLASS_CLEAN_WIN_MAE_R,
    CLASS_CLEAN_WIN_MFE_R,
    CLASS_IMMEDIATE_BARS,
    CLASS_IMMEDIATE_MFE_R,
)
from phase39.paths import build_signal_paths
from phase40.metrics import enrich_net

from phase36.outcomes import score_outcomes


def attach_outcome_labels(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    outcomes = score_outcomes(signals, market)
    paths = build_signal_paths(signals, market)
    paths = classify_dataframe(paths)

    pos = {ts: i for i, ts in enumerate(market.index)}
    df = signals.merge(outcomes, on=["signal_id", "marker_bar_timestamp", "signal_type"], how="left")
    df = df.merge(
        paths.drop(columns=[c for c in paths.columns if c in df.columns and c not in ("signal_id", "marker_bar_timestamp")]),
        on=["signal_id", "marker_bar_timestamp"],
        how="left",
        suffixes=("", "_path"),
    )
    df = enrich_net(df.assign(entry_price=df["entry_price"], stop_price=df["stop"], result_R=df["realized_R"]))

    # Secondary labels
    df["gross_R"] = df["realized_R"]
    df["positive_R"] = (df["net_R"] > 0).astype(int)
    df["R_ge_1"] = (df["net_R"] >= 1.0).astype(int)
    df["R_ge_2"] = (df["net_R"] >= 2.0).astype(int)
    df["target_hit"] = (df["exit_type"] == "TARGET").astype(int)
    df["stop_hit"] = (df["exit_type"] == "STOP").astype(int)
    df["MFE_minus_MAE"] = df["MFE_R"] - df["MAE_R"]
    df["clean_winner"] = (
        (df["MFE_R"] >= CLASS_CLEAN_WIN_MFE_R) & (df["MAE_R"] <= CLASS_CLEAN_WIN_MAE_R)
    ).astype(int)
    b50 = df["bars_to_plus_0.50r"].fillna(999)
    df["immediate_expansion"] = (
        (df["MFE_R"] >= CLASS_IMMEDIATE_MFE_R) & (b50 <= CLASS_IMMEDIATE_BARS)
    ).astype(int)
    df["wrong_direction"] = (df["behavior_class"] == "WRONG_DIRECTION").astype(int)

    # Entry bar index
    df["entry_bar_index"] = df["marker_bar_timestamp"].map(lambda t: pos.get(pd.Timestamp(t), np.nan))

    keep = [
        "signal_id",
        "marker_bar_timestamp",
        "timestamp_ct",
        "signal_type",
        "direction",
        "entry_price",
        "stop",
        "target",
        "atr",
        "architecture",
        "candidate_id",
        "event_id",
        "entry_bar_index",
        "impulse_3bar",
        "realized_R",
        "net_R",
        "gross_R",
        "MFE_R",
        "MAE_R",
        "MFE_minus_MAE",
        "exit_type",
        "target_hit",
        "stop_hit",
        "positive_R",
        "R_ge_1",
        "R_ge_2",
        "clean_winner",
        "immediate_expansion",
        "wrong_direction",
        "behavior_class",
        "directional_efficiency",
        "movement_efficiency",
        "bars_to_plus_0.50r",
        "bars_to_minus_0.50r",
        "source_displacement_time",
        "source_displacement_high",
        "source_displacement_low",
        "source_displacement_midpoint",
        "bos_or_reclaim_time",
        "bos_level",
        "retest_time",
        "reclaim_level",
    ]
    cols = [c for c in keep if c in df.columns]
    return df[cols + [c for c in df.columns if c.startswith("bars_to")]].drop_duplicates(subset=["signal_id"])
