"""Phase44 and Phase45 entry parity verification."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import performance
from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity

from .config import P45_ENTRY_PARITY, P45_WF
from .entries import load_frozen_entries


def verify_entry_parity() -> tuple[pd.DataFrame, dict, bool]:
    entries = load_frozen_entries()
    perf = performance(entries, col="control_net_R")
    fill_rate = len(entries) / len(pd.read_csv(P45_WF)) if P45_WF.exists() else 0.0
    wd = float(entries["control_wrong_direction"].mean()) if len(entries) else 0.0
    med_delay = float(entries["entry_delay_min"].median()) if len(entries) else 0.0
    ref = P45_ENTRY_PARITY
    ok = (
        abs(perf["N"] - ref["N"]) <= ref["tol_N"]
        and abs(perf["AvgR"] - ref["AvgR"]) <= ref["tol_AvgR"]
        and abs(perf["PF"] - ref["PF"]) <= ref["tol_PF"]
        and abs(fill_rate - ref["fill_rate"]) <= ref["tol_fill_rate"]
    )
    metrics = {**perf, "fill_rate": fill_rate, "wrong_direction": wd, "median_delay": med_delay}
    return entries, metrics, ok


def build_parity_csv() -> pd.DataFrame:
    signals = load_phase44_accepted()
    p44, _ = verify_phase44_parity(signals)
    _, e_metrics, e_ok = verify_entry_parity()
    rows = p44.to_dict("records")
    rows.extend([
        {"metric": "p44_parity_pass", "value": float(p44.loc[p44["metric"] == "parity_pass", "value"].iloc[0])},
        {"metric": "p45_entry_parity_pass", "value": float(e_ok)},
        {"metric": "p45_entry_N", "value": e_metrics["N"]},
        {"metric": "p45_entry_AvgR", "value": e_metrics["AvgR"]},
        {"metric": "p45_entry_PF", "value": e_metrics["PF"]},
        {"metric": "p45_entry_MaxDD", "value": e_metrics["MaxDD"]},
        {"metric": "p45_entry_fill_rate", "value": e_metrics["fill_rate"]},
        {"metric": "p45_entry_wrong_direction", "value": e_metrics["wrong_direction"]},
        {"metric": "p45_entry_median_delay", "value": e_metrics["median_delay"]},
    ])
    return pd.DataFrame(rows)
