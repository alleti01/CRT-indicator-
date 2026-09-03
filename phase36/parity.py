"""Compare replay signals against Phase 34 Pine-equivalent reference."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from .config import P34_COMBINED_REFERENCE

SIG_MAP = {
    "CONTINUATION_LONG": "L",
    "CONTINUATION_SHORT": "S",
    "REVERSAL_LONG": "RL",
    "REVERSAL_SHORT": "RS",
}
REV_SIG = frozenset({"RL", "RS"})
CONT_SIG = frozenset({"L", "S"})


def _norm_ts(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.floor("15min")


def _load_p34_reference() -> pd.DataFrame:
    if not P34_COMBINED_REFERENCE.exists():
        return pd.DataFrame()
    ref = pd.read_csv(P34_COMBINED_REFERENCE)
    ref["entry_time"] = _norm_ts(ref["entry_time"])
    ref["signal_type_code"] = ref["signal_type"].map(SIG_MAP)
    return ref


def compare_to_pine_reference(
    replay_signals: pd.DataFrame,
    *,
    overlap_start: str = "2018-01-01",
    overlap_end: str = "2026-06-26",
) -> pd.DataFrame:
    """Compare bar-by-bar replay vs Phase 34 Python reference (Pine contract baseline)."""
    ref = _load_p34_reference()
    if replay_signals.empty and ref.empty:
        return pd.DataFrame()

    rep = replay_signals.copy()
    rep["entry_time"] = _norm_ts(rep["marker_bar_timestamp"])

    rep = rep.loc[
        (rep["entry_time"] >= pd.Timestamp(overlap_start, tz="UTC"))
        & (rep["entry_time"] <= pd.Timestamp(overlap_end + " 23:59:59", tz="UTC"))
    ]
    ref = ref.loc[
        (ref["entry_time"] >= pd.Timestamp(overlap_start, tz="UTC"))
        & (ref["entry_time"] <= pd.Timestamp(overlap_end + " 23:59:59", tz="UTC"))
    ]

    rep_keys = set(zip(rep["entry_time"], rep["signal_type"])) if not rep.empty else set()
    ref_keys = set(zip(ref["entry_time"], ref["signal_type_code"])) if not ref.empty else set()

    rep_lookup = {(r.entry_time, r.signal_type): r for r in rep.itertuples(index=False)} if not rep.empty else {}
    ref_lookup = {(r.entry_time, r.signal_type_code): r for r in ref.itertuples(index=False)} if not ref.empty else {}

    rows = []
    for key in sorted(rep_keys | ref_keys, key=lambda x: (x[0], x[1])):
        ts, sig_type = key
        r_row = rep_lookup.get(key)
        p_row = ref_lookup.get(key)
        if r_row is not None and p_row is not None:
            status = "MATCH"
            if abs(float(r_row.entry_price) - float(p_row.entry_price)) > 0.05:
                status = "WRONG_ENTRY_PRICE"
            elif abs(float(r_row.stop) - float(p_row.stop_price)) > 0.05:
                status = "WRONG_STOP"
            elif abs(float(r_row.target) - float(p_row.target_price)) > 0.05:
                status = "WRONG_TARGET"
        elif r_row is not None:
            status = "EXTRA_PINE_SIGNAL"
        else:
            status = "MISSING_PINE_SIGNAL"
        rows.append(
            {
                "timestamp_ct": ts,
                "signal_type": sig_type,
                "python_replay_entry": getattr(r_row, "entry_price", np.nan) if r_row else np.nan,
                "pine_ref_entry": getattr(p_row, "entry_price", np.nan) if p_row else np.nan,
                "python_replay_stop": getattr(r_row, "stop", np.nan) if r_row else np.nan,
                "pine_ref_stop": getattr(p_row, "stop_price", np.nan) if p_row else np.nan,
                "python_replay_target": getattr(r_row, "target", np.nan) if r_row else np.nan,
                "pine_ref_target": getattr(p_row, "target_price", np.nan) if p_row else np.nan,
                "parity_status": status,
            }
        )
    return pd.DataFrame(rows)


def parity_summary(parity: pd.DataFrame) -> dict:
    if parity.empty:
        return {
            "matched": 0,
            "missing_pine": 0,
            "extra_pine": 0,
            "wrong_bar": 0,
            "price_mismatch": 0,
            "continuation_matched": 0,
            "reversal_matched": 0,
            "continuation_missing": 0,
            "reversal_missing": 0,
        }
    cont = parity.loc[parity["signal_type"].isin(CONT_SIG)]
    rev = parity.loc[parity["signal_type"].isin(REV_SIG)]
    return {
        "matched": int((parity["parity_status"] == "MATCH").sum()),
        "missing_pine": int((parity["parity_status"] == "MISSING_PINE_SIGNAL").sum()),
        "extra_pine": int((parity["parity_status"] == "EXTRA_PINE_SIGNAL").sum()),
        "wrong_bar": int((parity["parity_status"] == "WRONG_BAR").sum()),
        "price_mismatch": int(
            parity["parity_status"].isin(
                ("WRONG_ENTRY_PRICE", "WRONG_STOP", "WRONG_TARGET", "WRONG_DIRECTION")
            ).sum()
        ),
        "continuation_matched": int((cont["parity_status"] == "MATCH").sum()) if not cont.empty else 0,
        "reversal_matched": int((rev["parity_status"] == "MATCH").sum()) if not rev.empty else 0,
        "continuation_missing": int((cont["parity_status"] == "MISSING_PINE_SIGNAL").sum()) if not cont.empty else 0,
        "reversal_missing": int((rev["parity_status"] == "MISSING_PINE_SIGNAL").sum()) if not rev.empty else 0,
    }
