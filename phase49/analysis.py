"""Forward metrics, equity curve, checkpoints."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase31.metrics import max_drawdown, performance

from .bootstrap import forward_percentile
from .config import CHECKPOINTS, HISTORICAL
from phase48.entries import load_frozen_entries


def sample_status(n_fills: int) -> str:
    if n_fills < 20:
        return "TOO EARLY"
    if n_fills < 50:
        return "EARLY FORWARD OBSERVATION"
    if n_fills < 100:
        return "PRELIMINARY"
    if n_fills < 200:
        return "MEANINGFUL BUT NOT FINAL"
    return "STRONGER FORWARD EVIDENCE"


def forward_metrics(signals: pd.DataFrame, trades: pd.DataFrame) -> dict:
    n_p44 = len(signals)
    n_filled = int(signals["filled"].sum()) if not signals.empty and "filled" in signals.columns else 0
    n_unfilled = n_p44 - n_filled
    fill_rate = n_filled / n_p44 if n_p44 else 0.0
    if trades.empty:
        return {
            "phase44_signals": n_p44, "b1_fills": n_filled, "b1_unfilled": n_unfilled,
            "fill_rate": fill_rate, "closed_trades": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0,
            "MaxDD": 0.0, "WinRate": 0.0, "WrongDir": 0.0, "MedianDelay": np.nan,
            "MAE": np.nan, "MFE": np.nan, "AvgHold": np.nan,
        }
    p = performance(trades, col="net_r")
    wr = float((trades["net_r"] > 0).mean())
    wd = float(trades["wrong_direction"].mean()) if "wrong_direction" in trades.columns else 0.0
    med_delay = float(signals.loc[signals["filled"] == 1, "b1_delay"].median()) if n_filled and "b1_delay" in signals.columns else np.nan
    return {
        "phase44_signals": n_p44,
        "b1_fills": n_filled,
        "b1_unfilled": n_unfilled,
        "fill_rate": fill_rate,
        "closed_trades": p["N"],
        "AvgR": p["AvgR"],
        "MedianR": float(trades["net_r"].median()),
        "PF": p["PF"],
        "TotalR": p["TotalR"],
        "MaxDD": p["MaxDD"],
        "WinRate": wr,
        "LossRate": float((trades["net_r"] <= 0).mean()),
        "WrongDir": wd,
        "MedianDelay": med_delay,
        "MAE": float(trades["mae_r"].mean()),
        "MFE": float(trades["mfe_r"].mean()),
        "AvgHold": float(trades["hold_minutes"].mean()),
    }


def equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame(columns=["trade_number", "timestamp", "trade_r", "cumulative_r", "running_peak_r", "drawdown_r"])
    t = trades.sort_values("entry_time").reset_index(drop=True)
    cum = t["net_r"].cumsum()
    peak = cum.cummax()
    rows = []
    for i, row in t.iterrows():
        rows.append({
            "trade_number": i + 1,
            "timestamp": row["entry_time"],
            "trade_r": row["net_r"],
            "cumulative_r": cum.iloc[i],
            "running_peak_r": peak.iloc[i],
            "drawdown_r": peak.iloc[i] - cum.iloc[i],
            "roll_10_avg_r": cum.iloc[max(0, i - 9): i + 1].sum() / min(i + 1, 10) if i >= 0 else np.nan,
            "roll_20_avg_r": cum.iloc[max(0, i - 19): i + 1].sum() / min(i + 1, 20) if i >= 0 else np.nan,
        })
    return pd.DataFrame(rows)


def stratified_trades(trades: pd.DataFrame, col: str, vals: tuple) -> pd.DataFrame:
    rows = []
    for v in vals:
        sub = trades.loc[trades[col] == v] if not trades.empty else pd.DataFrame()
        p = performance(sub, col="net_r") if not sub.empty else {"N": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0, "MaxDD": 0.0}
        rows.append({"segment": v, **p, "WinRate": float((sub["net_r"] > 0).mean()) if len(sub) else 0.0})
    return pd.DataFrame(rows)


def checkpoint_reports(trades: pd.DataFrame, metrics: dict) -> tuple[pd.DataFrame, list[str]]:
    hist = load_frozen_entries()["control_net_R"].astype(float).to_numpy()
    rows = []
    md_parts = []
    for cp in CHECKPOINTS:
        sub = trades.head(cp) if len(trades) >= cp else trades
        p = performance(sub, col="net_r") if not sub.empty else {"N": 0, "AvgR": 0.0, "PF": 0.0, "TotalR": 0.0, "MaxDD": 0.0}
        reached = len(trades) >= cp
        pct_info = forward_percentile(sub["net_r"].to_numpy(), hist) if not sub.empty else {"AvgR_percentile": np.nan, "status": "INSUFFICIENT SAMPLE"}
        rows.append({"checkpoint": cp, "reached": reached, "N": len(sub), "AvgR": p["AvgR"], "PF": p["PF"], "TotalR": p["TotalR"], "MaxDD": p["MaxDD"], **pct_info})
        if reached or cp == CHECKPOINTS[0]:
            md_parts.append(_checkpoint_md(cp, sub, p, pct_info, metrics))
    return pd.DataFrame(rows), md_parts


def _checkpoint_md(cp: int, trades: pd.DataFrame, perf: dict, pct: dict, metrics: dict) -> str:
    return f"""# Checkpoint {cp}

N = {len(trades)}
AvgR = {perf.get('AvgR', 0):.3f}
PF = {perf.get('PF', 0):.2f}
TotalR = {perf.get('TotalR', 0):.1f}
MaxDD = {perf.get('MaxDD', 0):.2f}

Historical AvgR percentile: {pct.get('AvgR_percentile', 'N/A')}
Assessment: {pct.get('status', 'INSUFFICIENT SAMPLE')}

Forward fill rate: {metrics.get('fill_rate', 0):.1%}
"""


def primary_comparison_table(metrics: dict) -> pd.DataFrame:
    hist_b1 = HISTORICAL["b1"]
    hist_m0 = HISTORICAL["m0"]
    rows = [
        _row("Fill rate", hist_b1["fill_rate"], metrics.get("fill_rate"), metrics.get("b1_fills")),
        _row("AvgR", hist_b1["AvgR"], metrics.get("AvgR"), metrics.get("closed_trades")),
        _row("PF", hist_b1["PF"], metrics.get("PF"), metrics.get("closed_trades")),
        _row("TotalR", hist_m0["TotalR"], metrics.get("TotalR"), metrics.get("closed_trades")),
        _row("MaxDD", hist_b1["MaxDD"], metrics.get("MaxDD"), metrics.get("closed_trades")),
        _row("Win rate", hist_m0["WinRate"], metrics.get("WinRate"), metrics.get("closed_trades")),
        _row("WrongDir", hist_b1["wrong_direction"], metrics.get("WrongDir"), metrics.get("closed_trades")),
        _row("Median delay", hist_b1["median_delay"], metrics.get("MedianDelay"), metrics.get("b1_fills")),
        _row("MAE", np.nan, metrics.get("MAE"), metrics.get("closed_trades")),
        _row("MFE", np.nan, metrics.get("MFE"), metrics.get("closed_trades")),
        _row("Avg hold", np.nan, metrics.get("AvgHold"), metrics.get("closed_trades")),
    ]
    return pd.DataFrame(rows)


def _row(metric: str, hist, fwd, n) -> dict:
    n = int(n) if n and not (isinstance(n, float) and np.isnan(n)) else 0
    if n == 0:
        status = "INSUFFICIENT SAMPLE"
    elif isinstance(hist, float) and isinstance(fwd, float) and not np.isnan(hist) and not np.isnan(fwd):
        status = "WITHIN EXPECTED RANGE" if abs(fwd - hist) / max(abs(hist), 0.01) < 0.5 else "OBSERVE"
    else:
        status = "INSUFFICIENT SAMPLE"
    return {"METRIC": metric, "HISTORICAL_OOS": hist, "FORWARD": fwd, "FORWARD_N": n, "STATUS": status}
