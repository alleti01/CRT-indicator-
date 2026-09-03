"""Verify Phase44 and Phase45 B1 parity."""

from __future__ import annotations

import pandas as pd

from phase31.metrics import performance
from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity
from phase45.execution.walkforward import walk_forward_price

from .config import P44_PARITY, P45_B_PARITY, P45_DATASET, P45_WF


def verify_phase45_b1_from_file() -> tuple[pd.DataFrame, dict, bool]:
    wf = pd.read_csv(P45_WF, parse_dates=["marker_bar_timestamp", "actionable_timestamp"])
    filled = wf.loc[wf["B_filled"]]
    perf = performance(filled, col="B_net_R")
    fill_rate = len(filled) / len(wf) if len(wf) else 0.0
    wd = float(filled["B_wrong_direction"].mean()) if len(filled) else 0.0
    med_delay = float(filled["B_delay_min"].median()) if len(filled) else 0.0
    ref = P45_B_PARITY
    ok = (
        abs(perf["N"] - ref["N"]) <= ref["tol_N"]
        and abs(perf["AvgR"] - ref["AvgR"]) <= ref["tol_AvgR"]
        and abs(perf["PF"] - ref["PF"]) <= ref["tol_PF"]
        and abs(fill_rate - ref["fill_rate"]) <= ref["tol_fill_rate"]
    )
    metrics = {**perf, "fill_rate": fill_rate, "wrong_direction": wd, "median_delay": med_delay}
    return filled.copy(), metrics, ok


def verify_phase45_b1_recomputed() -> tuple[bool, dict]:
    ds = pd.read_csv(P45_DATASET, parse_dates=["marker_bar_timestamp", "actionable_timestamp"])
    stitched, _ = walk_forward_price(ds)
    filled = stitched.loc[stitched["B_filled"]]
    perf = performance(filled, col="B_net_R")
    ref = P45_B_PARITY
    ok = abs(perf["N"] - ref["N"]) <= ref["tol_N"] and abs(perf["AvgR"] - ref["AvgR"]) <= ref["tol_AvgR"]
    return ok, perf


def build_parity_csv() -> pd.DataFrame:
    signals = load_phase44_accepted()
    p44, _ = verify_phase44_parity(signals)
    _, b_metrics, b_ok = verify_phase45_b1_from_file()
    recompute_ok, recompute_perf = verify_phase45_b1_recomputed()
    rows = p44.to_dict("records")
    rows.extend([
        {"metric": "p44_parity_pass", "value": float(p44.loc[p44["metric"] == "parity_pass", "value"].iloc[0])},
        {"metric": "p45_b1_parity_pass", "value": float(b_ok and recompute_ok)},
        {"metric": "p45_b1_N", "value": b_metrics["N"]},
        {"metric": "p45_b1_AvgR", "value": b_metrics["AvgR"]},
        {"metric": "p45_b1_PF", "value": b_metrics["PF"]},
        {"metric": "p45_b1_MaxDD", "value": b_metrics["MaxDD"]},
        {"metric": "p45_b1_fill_rate", "value": b_metrics["fill_rate"]},
        {"metric": "p45_b1_wrong_direction", "value": b_metrics["wrong_direction"]},
        {"metric": "p45_b1_median_delay", "value": b_metrics["median_delay"]},
        {"metric": "p45_recompute_N", "value": recompute_perf["N"]},
        {"metric": "p45_recompute_AvgR", "value": recompute_perf["AvgR"]},
    ])
    return pd.DataFrame(rows)
