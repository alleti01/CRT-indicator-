"""Historical parity gate before forward processing."""

from __future__ import annotations

import pandas as pd

from phase31.metrics import performance
from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity

from phase48.entries import load_frozen_entries
from phase48.parity import verify_entry_parity

from .config import HISTORICAL, P48_CONTROL


def verify_m0_parity() -> tuple[dict, bool]:
    if not P48_CONTROL.exists():
        df = load_frozen_entries()
        perf = performance(df, col="control_net_R")
        wr = float((df["control_net_R"] > 0).mean()) if len(df) else 0.0
    else:
        df = pd.read_csv(P48_CONTROL)
        perf = performance(df, col="net_R")
        wr = float((df["net_R"] > 0).mean()) if len(df) else 0.0
    ref = HISTORICAL["m0"]
    ok = (
        abs(perf["N"] - ref["N"]) <= 5
        and abs(perf["TotalR"] - ref["TotalR"]) <= 5.0
        and abs(wr - ref["WinRate"]) <= 0.02
    )
    return {**perf, "WinRate": wr}, ok


def build_historical_parity_csv() -> pd.DataFrame:
    signals = load_phase44_accepted()
    p44, _ = verify_phase44_parity(signals)
    _, b_metrics, b_ok = verify_entry_parity()
    m0_metrics, m0_ok = verify_m0_parity()
    rows = p44.to_dict("records")
    rows.extend([
        {"metric": "p44_parity_pass", "value": float(p44.loc[p44["metric"] == "parity_pass", "value"].iloc[0])},
        {"metric": "p45_b1_parity_pass", "value": float(b_ok)},
        {"metric": "p45_b1_N", "value": b_metrics["N"]},
        {"metric": "p45_b1_AvgR", "value": b_metrics["AvgR"]},
        {"metric": "p45_b1_PF", "value": b_metrics["PF"]},
        {"metric": "m0_parity_pass", "value": float(m0_ok)},
        {"metric": "m0_N", "value": m0_metrics["N"]},
        {"metric": "m0_TotalR", "value": m0_metrics["TotalR"]},
        {"metric": "m0_WinRate", "value": m0_metrics["WinRate"]},
        {"metric": "all_parity_pass", "value": float(
            bool(p44.loc[p44["metric"] == "parity_pass", "value"].iloc[0]) and b_ok and m0_ok
        )},
    ])
    return pd.DataFrame(rows)


def parity_passes() -> bool:
    df = build_historical_parity_csv()
    return bool(df.loc[df["metric"] == "all_parity_pass", "value"].iloc[0])
