"""Phase64 — original direction diagnostic vs location-only."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _merge_events_paths(events: pd.DataFrame, paths: pd.DataFrame) -> pd.DataFrame:
    return events[["signal_i", "direction", "atr"]].rename(columns={"atr": "event_atr"}).merge(
        paths, left_on="signal_i", right_on="event_i", how="inner",
    )


def direction_diagnostics(events: pd.DataFrame, paths: pd.DataFrame) -> dict:
    """Compare original Phase58 direction to symmetric path outcomes."""
    df = _merge_events_paths(events, paths)
    if df.empty:
        return {}
    out = {}

    fs = df["first_0.5"]
    d = df["direction"]
    valid_fs = fs.isin(["UP", "DOWN"])
    first_ok = ((fs == "UP") & (d == "LONG")) | ((fs == "DOWN") & (d == "SHORT"))
    out["first_side_accuracy"] = float(first_ok[valid_fs].mean()) if valid_fs.any() else 0

    up, dn = df["up_60m"], df["dn_60m"]
    valid_lg = (up - dn).abs() >= 0.25
    largest_ok = ((up > dn) & (d == "LONG")) | ((dn > up) & (d == "SHORT"))
    out["largest_side_accuracy"] = float(largest_ok[valid_lg].mean()) if valid_lg.any() else 0

    clean_mask = df["clean_up"] | df["clean_dn"]
    clean_ok = (df["clean_up"] & (d == "LONG")) | (df["clean_dn"] & (d == "SHORT"))
    out["clean_expansion_accuracy"] = float(clean_ok[clean_mask].mean()) if clean_mask.any() else 0

    arch = df["archetype"]
    sweep_mask = arch.isin(["TWO_SIDED_SWEEP_THEN_UP", "TWO_SIDED_SWEEP_THEN_DOWN"])
    sweep_ok = (arch == "TWO_SIDED_SWEEP_THEN_UP") & (d == "LONG") | (arch == "TWO_SIDED_SWEEP_THEN_DOWN") & (d == "SHORT")
    out["post_sweep_direction_accuracy"] = float(sweep_ok[sweep_mask].mean()) if sweep_mask.any() else 0

    out["incremental_first_side"] = out["first_side_accuracy"] - 0.5
    out["incremental_largest_side"] = out["largest_side_accuracy"] - 0.5

    if out["first_side_accuracy"] < 0.53 and out["largest_side_accuracy"] < 0.53:
        out["incremental_label"] = "NONE"
    elif out["largest_side_accuracy"] < 0.55:
        out["incremental_label"] = "SMALL"
    elif out["largest_side_accuracy"] < 0.60:
        out["incremental_label"] = "MODERATE"
    else:
        out["incremental_label"] = "LARGE"
    return out


def first_bar_info(events: pd.DataFrame, paths: pd.DataFrame, hi, lo, op, cl) -> dict:
    """0-1 bar diagnostic — information only."""
    df = _merge_events_paths(events, paths)
    if df.empty:
        return {}
    ei = df["signal_i"].astype(int).values
    body = cl[ei] - op[ei]
    fs = df["first_0.5"].values
    d = df["direction"].values

    up_mask = (fs == "UP") & (body > 0)
    dn_mask = (fs == "DOWN") & (body < 0)
    up_ok = up_mask & ((d == "LONG"))
    dn_ok = dn_mask & ((d == "SHORT"))
    return {
        "bar0_aligns_first_break_up": float(up_ok.sum() / up_mask.sum()) if up_mask.sum() else 0,
        "bar0_aligns_first_break_dn": float(dn_ok.sum() / dn_mask.sum()) if dn_mask.sum() else 0,
    }
