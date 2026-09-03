"""Reversal and continuation episode analytics."""

from __future__ import annotations

import pandas as pd

from phase53.research.metrics import summarize_r
from phase56.config import LOGS, RESULTS


def reversal_continuation_results() -> tuple[pd.DataFrame, pd.DataFrame]:
    sig = pd.read_csv(LOGS / "s54_forward_signals.csv")
    tr = pd.read_csv(LOGS / "s54_forward_trades.csv")
    if sig.empty:
        return pd.DataFrame(), pd.DataFrame()
    sig["timestamp_ct"] = sig["timestamp_ct"].map(pd.Timestamp)
    tr["entry_timestamp"] = tr["entry_timestamp"].map(pd.Timestamp)
    tr["net_R"] = tr["net_R"].astype(float)
    tr = tr.merge(sig[["signal_id", "timestamp_ct", "direction"]], on="signal_id", suffixes=("", "_sig"))
    tr = tr.sort_values("timestamp_ct").reset_index(drop=True)

    rev_rows = []
    cont_rows = []
    for i in range(1, len(tr)):
        prev, cur = tr.iloc[i - 1], tr.iloc[i]
        gap = (cur["timestamp_ct"] - prev["timestamp_ct"]).total_seconds() / 60.0
        if prev["direction"] != cur["direction"]:
            rev_rows.append({"gap_min": gap, "net_R": cur["net_R"], "from": prev["direction"], "to": cur["direction"]})
        else:
            cont_rows.append({"gap_min": gap, "net_R": cur["net_R"], "direction": cur["direction"]})

    rev = pd.DataFrame(rev_rows)
    cont = pd.DataFrame(cont_rows)
    if len(rev):
        rev_out = pd.DataFrame([{"type": "REVERSAL", "N": len(rev), "AvgR": float(rev["net_R"].mean()), "median_gap_min": float(rev["gap_min"].median())}])
    else:
        rev_out = pd.DataFrame([{"type": "REVERSAL", "N": 0}])
    if len(cont):
        cont_out = pd.DataFrame([{"type": "CONTINUATION", "N": len(cont), "AvgR": float(cont["net_R"].mean()), "median_gap_min": float(cont["gap_min"].median())}])
    else:
        cont_out = pd.DataFrame([{"type": "CONTINUATION", "N": 0}])
    rev_out.to_csv(RESULTS / "reversal_results.csv", index=False)
    cont_out.to_csv(RESULTS / "continuation_results.csv", index=False)
    return rev_out, cont_out
