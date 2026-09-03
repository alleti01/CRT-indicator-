"""Phase 45 / B0 baseline reproduction."""

from __future__ import annotations

import pandas as pd

from phase31.metrics import performance
from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity

from .config import B0_PREFIX, B0_WINDOW_MIN, P44_PARITY, P45_B_PARITY, P45_DATASET, WALK_FORWARD_FOLDS


def _slice_oos(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    ts = pd.to_datetime(df["marker_bar_timestamp"])
    tz = ts.dt.tz
    lo = pd.Timestamp(start, tz=tz)
    hi = pd.Timestamp(end, tz=tz)
    return df.loc[(ts >= lo) & (ts <= hi)].copy()


def build_oos_frame(dataset: pd.DataFrame | None = None) -> pd.DataFrame:
    """Stitched OOS TEST segments (2020+) from Phase45 dataset."""
    ds = pd.read_csv(P45_DATASET, parse_dates=["marker_bar_timestamp", "actionable_timestamp"]) if dataset is None else dataset.copy()
    parts = []
    for fold_i, (_tr_s, _tr_e, te_s, te_e) in enumerate(WALK_FORWARD_FOLDS, 1):
        test = _slice_oos(ds, te_s, te_e)
        if test.empty:
            continue
        test["fold"] = fold_i
        test["test_start"] = te_s
        test["test_end"] = te_e
        parts.append(test)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def apply_b0(df: pd.DataFrame) -> pd.DataFrame:
    """Map frozen B1 @ 10 min to B0 columns."""
    out = df.copy()
    p = B0_PREFIX
    out["B0_filled"] = out[f"{p}_filled"].astype(bool)
    for src, dst in (
        (f"{p}_net_R", "B0_net_R"),
        (f"{p}_gross_R", "B0_gross_R"),
        (f"{p}_MFE_R", "B0_MFE_R"),
        (f"{p}_MAE_R", "B0_MAE_R"),
        (f"{p}_delay_min", "B0_delay_min"),
        (f"{p}_entry_price", "B0_entry_price"),
        (f"{p}_entry_time", "B0_entry_time"),
        (f"{p}_wrong_direction", "B0_wrong_direction"),
        (f"{p}_exit_type", "B0_exit_type"),
    ):
        if src in out.columns:
            out[dst] = out[src]
    out["B0_rule"] = "B1"
    out["B0_window"] = B0_WINDOW_MIN
    return out


def verify_p45_parity(b0_oos: pd.DataFrame) -> pd.DataFrame:
    """Verify Phase44 full parity and document B0 B1@10m vs Phase45 WF reference."""
    signals = load_phase44_accepted()
    p44, _ = verify_phase44_parity(signals)
    filled = b0_oos.loc[b0_oos["B0_filled"]]
    perf = performance(filled, col="B0_net_R")
    fill_rate = len(filled) / len(b0_oos) if len(b0_oos) else 0.0
    ref = P45_B_PARITY
    # B0 is fixed B1@10m; Phase45 WF used mixed 5/10m windows per fold (N=1135 reference)
    wf_ref_match = (
        abs(perf["N"] - ref["N"]) <= ref["tol_N"]
        and abs(perf["AvgR"] - ref["AvgR"]) <= ref["tol_AvgR"]
        and abs(fill_rate - ref["fill_rate"]) <= ref["tol_fill_rate"]
    )
    rows = p44.to_dict("records")
    rows.extend(
        [
            {"metric": "p44_parity_pass", "value": float(p44.loc[p44["metric"] == "parity_pass", "value"].iloc[0])},
            {"metric": "b0_b1_w10_N", "value": perf["N"]},
            {"metric": "b0_b1_w10_AvgR", "value": perf["AvgR"]},
            {"metric": "b0_b1_w10_PF", "value": perf["PF"]},
            {"metric": "b0_b1_w10_MaxDD", "value": perf["MaxDD"]},
            {"metric": "b0_b1_w10_fill_rate", "value": fill_rate},
            {"metric": "p45_wf_reference_N", "value": ref["N"]},
            {"metric": "p45_wf_reference_AvgR", "value": ref["AvgR"]},
            {"metric": "p45_wf_mixed_window_match", "value": float(wf_ref_match)},
            {"metric": "b0_control", "value": 1.0},
            {"metric": "b0_note", "value": 0.0},
        ]
    )
    return pd.DataFrame(rows)


def verify_phase45_wf_parity() -> tuple[bool, dict]:
    """Compare B1_w10 OOS to Phase45 WF Model B reference."""
    oos = apply_b0(build_oos_frame())
    filled = oos.loc[oos["B0_filled"]]
    perf = performance(filled, col="B0_net_R")
    fill_rate = len(filled) / len(oos) if len(oos) else 0.0
    ref = P45_B_PARITY
    ok = (
        abs(perf["N"] - ref["N"]) <= ref["tol_N"]
        and abs(perf["AvgR"] - ref["AvgR"]) <= ref["tol_AvgR"]
        and abs(perf["PF"] - ref["PF"]) <= ref["tol_PF"]
        and abs(fill_rate - ref["fill_rate"]) <= ref["tol_fill_rate"]
    )
    return ok, {**perf, "fill_rate": fill_rate}
