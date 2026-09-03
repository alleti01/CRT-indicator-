"""Phase 44 accepted signals with causal timestamps."""

from __future__ import annotations

import pandas as pd

from phase31.metrics import performance
from phase36.data import load_replay_market_15m
from phase39.classify import classify_dataframe
from phase39.paths import build_signal_paths

from .config import CHART_15M, P44_REF, P44_PARITY


def load_phase44_accepted() -> pd.DataFrame:
    ref = pd.read_csv(P44_REF, parse_dates=["timestamp"])
    acc = ref.loc[ref["accepted"]].copy()
    acc["marker_bar_timestamp"] = pd.to_datetime(acc["timestamp"], utc=True)
    acc["entry_price"] = acc["entry"]
    acc["signal_id"] = acc["signal_id"].astype(int)
    acc["actionable_timestamp"] = acc["marker_bar_timestamp"] + pd.Timedelta(minutes=CHART_15M)
    acc["first_eligible_1m"] = acc["actionable_timestamp"]
    return acc.sort_values("marker_bar_timestamp").reset_index(drop=True)


def verify_phase44_parity(signals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Verify accepted population matches frozen Phase 44 manifest."""
    counts = {
        "L": int((signals["signal_type"] == "L").sum()),
        "S": int((signals["signal_type"] == "S").sum()),
        "RL": int((signals["signal_type"] == "RL").sum()),
        "RS": int((signals["signal_type"] == "RS").sum()),
        "total": int(len(signals)),
    }
    perf = performance(signals, col="net_R")
    tol = P44_PARITY
    parity_ok = (
        counts["total"] == tol["N"]
        and abs(perf["AvgR"] - tol["AvgR"]) <= tol["tol_AvgR"]
        and abs(perf["PF"] - tol["PF"]) <= tol["tol_PF"]
        and abs(perf["TotalR"] - tol["TotalR"]) <= tol["tol_TotalR"]
        and abs(perf["MaxDD"] - tol["MaxDD"]) <= tol["tol_MaxDD"]
    )
    rows = [
        {"metric": "parity_pass", "value": float(parity_ok)},
        {"metric": "L", "value": counts["L"]},
        {"metric": "S", "value": counts["S"]},
        {"metric": "RL", "value": counts["RL"]},
        {"metric": "RS", "value": counts["RS"]},
        {"metric": "total", "value": counts["total"]},
        {"metric": "AvgR", "value": perf["AvgR"]},
        {"metric": "PF", "value": perf["PF"]},
        {"metric": "TotalR", "value": perf["TotalR"]},
        {"metric": "MaxDD", "value": perf["MaxDD"]},
        {"metric": "N", "value": perf["N"]},
    ]
    return pd.DataFrame(rows), signals.copy()


def attach_behavior_15m(signals: pd.DataFrame) -> pd.DataFrame:
    market = load_replay_market_15m()
    sig = signals.copy()
    sig["entry_price"] = sig["entry"]
    paths = build_signal_paths(sig, market)
    paths = classify_dataframe(paths)
    cols = [
        "signal_id",
        "behavior_class",
        "MFE_R",
        "MAE_R",
        "bars_to_plus_0.50r",
        "bars_to_plus_1.00r",
        "bars_to_target",
        "exit_type",
    ]
    out = sig.merge(paths[cols], on="signal_id", how="left")
    out["wrong_direction"] = (out["behavior_class"] == "WRONG_DIRECTION").astype(int)
    return out
