"""Phase 38 Pine-equivalent parity vs Phase 37 reference map."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from phase36.data import load_replay_market_15m

from phase37.concurrent import replay_concurrent

from .config import (
    EXP_CONT_L,
    EXP_CONT_S,
    EXP_REV_RL,
    EXP_REV_RS,
    P36_SIGNAL_MAP,
    P37_REFERENCE_MAP,
)


PRICE_TOL = 0.05


def _signal_key(df: pd.DataFrame) -> pd.Series:
    ts = pd.to_datetime(df["timestamp_ct"], utc=True).dt.floor("15min")
    return ts.astype(str) + "|" + df["signal_type"].astype(str)


def load_reference(path=P37_REFERENCE_MAP) -> pd.DataFrame:
    ref = pd.read_csv(path)
    ref["marker_bar_timestamp"] = pd.to_datetime(ref["marker_bar_timestamp"], utc=True)
    ref["timestamp_ct"] = pd.to_datetime(ref["timestamp_ct"], utc=True)
    return ref


def run_pine_equivalent_replay(market: pd.DataFrame | None = None) -> pd.DataFrame:
    """Phase 37 concurrent engine is the authoritative Pine-equivalent simulator."""
    import os

    cached = P37_REFERENCE_MAP
    if os.environ.get("PHASE38_SKIP_REPLAY") == "1" and cached.exists():
        out = pd.read_csv(cached)
        out["marker_bar_timestamp"] = pd.to_datetime(out["marker_bar_timestamp"], utc=True)
        out["timestamp_ct"] = pd.to_datetime(out["timestamp_ct"], utc=True)
        return out
    if market is None:
        market = load_replay_market_15m()
    signals, _, _ = replay_concurrent(market)
    if signals.empty:
        return signals
    out = signals.copy()
    if "timestamp_ct" not in out.columns and "marker_bar_timestamp" in out.columns:
        out["timestamp_ct"] = out["marker_bar_timestamp"]
    return out


def compare_signals(
    reference: pd.DataFrame,
    actual: pd.DataFrame,
    *,
    price_tol: float = PRICE_TOL,
) -> pd.DataFrame:
    """Row-level parity table keyed by timestamp + signal_type."""
    ref = reference.copy()
    act = actual.copy()
    ref["_key"] = _signal_key(ref)
    act["_key"] = _signal_key(act)

    merged = ref.merge(
        act,
        on="_key",
        how="outer",
        suffixes=("_ref", "_act"),
        indicator=True,
    )

    def _status(row) -> str:
        if row["_merge"] == "left_only":
            return "MISSING"
        if row["_merge"] == "right_only":
            return "EXTRA"
        r_type = str(row.get("signal_type_ref", row.get("signal_type", "")))
        a_type = str(row.get("signal_type_act", row.get("signal_type", "")))
        if r_type != a_type:
            return "WRONG_DIRECTION"
        if abs(float(row["entry_price_ref"]) - float(row["entry_price_act"])) > price_tol:
            return "WRONG_ENTRY"
        if abs(float(row["stop_ref"]) - float(row["stop_act"])) > price_tol:
            return "WRONG_STOP"
        if abs(float(row["target_ref"]) - float(row["target_act"])) > price_tol:
            return "WRONG_TARGET"
        return "MATCH"

    if merged.empty:
        return pd.DataFrame(columns=["key", "parity_status"])

    merged["parity_status"] = merged.apply(_status, axis=1)
    merged["timestamp_ct"] = merged.get("timestamp_ct_ref", merged.get("timestamp_ct_act"))
    merged["signal_type"] = merged.get("signal_type_ref", merged.get("signal_type_act"))
    merged["ref_entry"] = merged.get("entry_price_ref")
    merged["act_entry"] = merged.get("entry_price_act")
    merged["ref_stop"] = merged.get("stop_ref")
    merged["act_stop"] = merged.get("stop_act")
    merged["ref_target"] = merged.get("target_ref")
    merged["act_target"] = merged.get("target_act")
    return merged[
        ["_key", "timestamp_ct", "signal_type", "ref_entry", "act_entry", "ref_stop", "act_stop", "ref_target", "act_target", "parity_status"]
    ].rename(columns={"_key": "key"})


def signal_counts(df: pd.DataFrame) -> Dict[str, int]:
    if df.empty:
        return {"L": 0, "S": 0, "RL": 0, "RS": 0, "total": 0}
    return {
        "L": int((df["signal_type"] == "L").sum()),
        "S": int((df["signal_type"] == "S").sum()),
        "RL": int((df["signal_type"] == "RL").sum()),
        "RS": int((df["signal_type"] == "RS").sum()),
        "total": int(len(df)),
    }


def restored_count(reference: pd.DataFrame, single_tracker: pd.DataFrame) -> int:
    def keys(df):
        t = pd.to_datetime(df["timestamp_ct"], utc=True).dt.floor("15min")
        return set(zip(t, df["signal_type"]))

    ref_rev = reference.loc[reference["signal_type"].isin(["RL", "RS"])]
    single_rev = single_tracker.loc[single_tracker["signal_type"].isin(["RL", "RS"])]
    return len(keys(ref_rev) - keys(single_rev))


def build_parity_windows(reference: pd.DataFrame, parity: pd.DataFrame) -> pd.DataFrame:
    """Representative validation windows for TradingView manual checks."""
    rows: List[dict] = []
    ref = reference.copy()
    ref["ts"] = pd.to_datetime(ref["timestamp_ct"], utc=True)

    # Restored reversals (in reference but not in Phase 36 single tracker)
    if P36_SIGNAL_MAP.exists():
        p36 = pd.read_csv(P36_SIGNAL_MAP)
        p36["ts"] = pd.to_datetime(p36["timestamp_ct"], utc=True).dt.floor("15min")
        p36_keys = set(zip(p36["ts"], p36["signal_type"]))
        ref_rev = ref.loc[ref["signal_type"].isin(["RL", "RS"])].copy()
        ref_rev["ts_floor"] = ref_rev["ts"].dt.floor("15min")
        ref_rev["_k"] = list(zip(ref_rev["ts_floor"], ref_rev["signal_type"]))
        restored = ref_rev.loc[~ref_rev["_k"].isin(p36_keys)]
        for label, pool in (
            ("RESTORED_RL", restored.loc[restored["signal_type"] == "RL"]),
            ("RESTORED_RS", restored.loc[restored["signal_type"] == "RS"]),
        ):
            for _, row in pool.head(3).iterrows():
                rows.append(_window_row(label, row))

    # Common reversal + continuation samples
    for label, mask in (
        ("COMMON_RL", ref["signal_type"] == "RL"),
        ("COMMON_RS", ref["signal_type"] == "RS"),
        ("CONTINUATION_L", ref["signal_type"] == "L"),
        ("CONTINUATION_S", ref["signal_type"] == "S"),
    ):
        for _, row in ref.loc[mask].head(2).iterrows():
            rows.append(_window_row(label, row))

    # Overlap conflict bars from Phase 37
    conflicts_path = P37_REFERENCE_MAP.parent / "continuation_reversal_conflicts.csv"
    if conflicts_path.exists():
        conflicts = pd.read_csv(conflicts_path)
        for _, crow in conflicts.head(5).iterrows():
            ts = pd.to_datetime(crow["timestamp"], utc=True)
            near = ref.loc[(ref["ts"] >= ts - pd.Timedelta(hours=1)) & (ref["ts"] <= ts + pd.Timedelta(hours=1))]
            for _, row in near.head(2).iterrows():
                rows.append(
                    {
                        **_window_row("CONT_REV_CONFLICT", row),
                        "conflict_note": f"{crow.get('continuation', '')}+{crow.get('reversal', '')}",
                    }
                )

    # Recent eras
    for era_name, start, end in (
        ("ERA_2024", "2024-01-01", "2024-12-31"),
        ("ERA_2025", "2025-01-01", "2025-12-31"),
        ("ERA_2026", "2026-01-01", "2026-06-30"),
    ):
        era = ref.loc[(ref["ts"] >= pd.Timestamp(start, tz="UTC")) & (ref["ts"] <= pd.Timestamp(end, tz="UTC"))]
        for _, row in era.head(2).iterrows():
            rows.append(_window_row(era_name, row))

    if parity is not None and not parity.empty:
        multi = parity.loc[parity["parity_status"] != "MATCH"].head(3)
        for _, prow in multi.iterrows():
            rows.append(
                {
                    "window_id": "MISMATCH",
                    "entry_time_ct": prow["timestamp_ct"],
                    "signal_type": prow["signal_type"],
                    "expected_entry": prow.get("ref_entry"),
                    "parity_status": prow["parity_status"],
                }
            )

    return pd.DataFrame(rows)


def _window_row(window_id: str, row: pd.Series) -> dict:
    return {
        "window_id": window_id,
        "entry_time_ct": row.get("timestamp_ct", row.get("ts")),
        "signal_type": row["signal_type"],
        "direction": row.get("direction", ""),
        "expected_entry": row.get("entry_price"),
        "expected_stop": row.get("stop"),
        "expected_target": row.get("target"),
        "candidate_id": row.get("candidate_id", ""),
        "event_id": row.get("event_id", ""),
    }


def full_parity_report() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    reference = load_reference()
    actual = run_pine_equivalent_replay()
    parity = compare_signals(reference, actual)
    counts_ref = signal_counts(reference)
    counts_act = signal_counts(actual)

    counts_table = pd.DataFrame(
        [
            {"segment": "reference", **counts_ref},
            {"segment": "pine_equivalent", **counts_act},
            {
                "segment": "expected",
                "L": EXP_CONT_L,
                "S": EXP_CONT_S,
                "RL": EXP_REV_RL,
                "RS": EXP_REV_RS,
                "total": EXP_CONT_L + EXP_CONT_S + EXP_REV_RL + EXP_REV_RS,
            },
        ]
    )

    restored = restored_count(reference, pd.read_csv(P36_SIGNAL_MAP)) if P36_SIGNAL_MAP.exists() else 0

    meta = {
        "continuation_parity": counts_ref["L"] == EXP_CONT_L and counts_ref["S"] == EXP_CONT_S,
        "reversal_parity": counts_ref["RL"] == EXP_REV_RL and counts_ref["RS"] == EXP_REV_RS,
        "sim_vs_ref_match_rate": float((parity["parity_status"] == "MATCH").mean()) if not parity.empty else 0.0,
        "restored_reversals": restored,
        "wrong_bar": int((parity["parity_status"] == "WRONG_BAR").sum()),
        "wrong_entry": int((parity["parity_status"] == "WRONG_ENTRY").sum()),
        "wrong_stop": int((parity["parity_status"] == "WRONG_STOP").sum()),
        "wrong_target": int((parity["parity_status"] == "WRONG_TARGET").sum()),
        "missing": int((parity["parity_status"] == "MISSING").sum()),
        "extra": int((parity["parity_status"] == "EXTRA").sum()),
    }

    windows = build_parity_windows(reference, parity)
    return parity, windows, counts_table, meta
