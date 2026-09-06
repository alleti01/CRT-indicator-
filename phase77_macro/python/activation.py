"""Layer activation and confluence distribution by observation universe."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from phase77.python.setups import _layer_flags, confluence_count


STATE_COLS = (
    "auction_state", "location_type", "structure_state", "price_response",
    "absorption_proxy", "acceptance_state", "confirmation_state",
)

KEY_STATES = {
    "BUYING_INEFFICIENT": ("price_response", "BUYING_INEFFICIENT"),
    "SELLING_INEFFICIENT": ("price_response", "SELLING_INEFFICIENT"),
    "BUYING_ABSORBED_PROXY": ("absorption_proxy", "BUYING_ABSORBED_PROXY"),
    "SELLING_ABSORBED_PROXY": ("absorption_proxy", "SELLING_ABSORBED_PROXY"),
    "UPPER_REJECTION": ("acceptance_state", "UPPER_REJECTION"),
    "LOWER_REJECTION": ("acceptance_state", "LOWER_REJECTION"),
    "ACCEPTANCE_UP": ("acceptance_state", "ACCEPTANCE_UP"),
    "ACCEPTANCE_DOWN": ("acceptance_state", "ACCEPTANCE_DOWN"),
    "FAILED_ACCEPTANCE_UP": ("acceptance_state", "FAILED_ACCEPTANCE_UP"),
    "FAILED_ACCEPTANCE_DOWN": ("acceptance_state", "FAILED_ACCEPTANCE_DOWN"),
    "CONFIRMED_LONG": ("confirmation_state", "CONFIRMED_LONG"),
    "CONFIRMED_SHORT": ("confirmation_state", "CONFIRMED_SHORT"),
}


def _state_rates(df: pd.DataFrame) -> dict[str, float]:
    n = len(df)
    if n == 0:
        return {"n_bars": 0}
    out: dict[str, Any] = {"n_bars": n, "n_sessions": df["session_date"].nunique() if "session_date" in df else 0}
    for col in STATE_COLS:
        if col in df.columns:
            vc = df[col].value_counts(normalize=True)
            for k, v in vc.head(12).items():
                out[f"{col}:{k}"] = float(v)
    for label, (col, val) in KEY_STATES.items():
        if col in df.columns:
            out[label] = float((df[col] == val).mean())
    return out


def confluence_distribution(feat: pd.DataFrame) -> dict[int, int]:
    """Confluence 0-7 among bars with confirmed direction."""
    dist = {i: 0 for i in range(8)}
    sub = feat[feat["confirmation_state"].isin(("CONFIRMED_LONG", "CONFIRMED_SHORT"))]
    for _, row in sub.iterrows():
        d = "LONG" if row["confirmation_state"] == "CONFIRMED_LONG" else "SHORT"
        cc = confluence_count(row, d)
        dist[cc] = dist.get(cc, 0) + 1
    return dist


def activation_report(
    feat: pd.DataFrame,
    macro_mask: pd.Series,
    same_time_mask: pd.Series,
    baseline_mask: pd.Series,
) -> dict:
    groups = {
        "MACRO": feat.loc[macro_mask],
        "SAME_TIME_CONTROL": feat.loc[same_time_mask],
        "ORDINARY_BASELINE": feat.loc[baseline_mask],
    }
    rates = {name: _state_rates(df) for name, df in groups.items()}
    lifts = {}
    macro_r = rates.get("MACRO", {})
    for key in KEY_STATES:
        m = macro_r.get(key, 0)
        st = rates.get("SAME_TIME_CONTROL", {}).get(key, 0)
        bl = rates.get("ORDINARY_BASELINE", {}).get(key, 0)
        lifts[f"{key}_vs_same_time"] = m / st if st > 0 else (np.inf if m > 0 else 1.0)
        lifts[f"{key}_vs_baseline"] = m / bl if bl > 0 else (np.inf if m > 0 else 1.0)
    conf = {name: confluence_distribution(df) for name, df in groups.items()}
    return {"rates": rates, "lifts": lifts, "confluence": conf}


def setup_counts_by_group(
    signals: pd.DataFrame,
    bar_index: pd.DatetimeIndex,
    macro_mask: pd.Series,
    same_time_mask: pd.Series,
    baseline_mask: pd.Series,
) -> dict:
    if signals.empty:
        return {"MACRO": {}, "SAME_TIME_CONTROL": {}, "ORDINARY_BASELINE": {}}
    ts_macro = set(bar_index[macro_mask.fillna(False)])
    ts_same = set(bar_index[same_time_mask.fillna(False)])
    ts_base = set(bar_index[baseline_mask.fillna(False)])
    out = {}
    for name, ts_set in (
        ("MACRO", ts_macro),
        ("SAME_TIME_CONTROL", ts_same),
        ("ORDINARY_BASELINE", ts_base),
    ):
        sub = signals[signals["signal_ts"].isin(ts_set)]
        out[name] = sub.groupby("setup").size().to_dict() if len(sub) else {}
        out[f"{name}_total"] = len(sub)
    return out
