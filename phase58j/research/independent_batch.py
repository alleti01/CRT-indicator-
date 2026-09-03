"""Batch independent simulation with cost normalization."""
from __future__ import annotations

import pandas as pd

from phase58.research.instrument import NQ
from phase58j.research.independent_simulator import simulate_bar_path


def simulate_trades_independent(m, trades: pd.DataFrame, stop_atr: float, cfg: dict) -> pd.DataFrame:
    rows = []
    hold = cfg.get("max_hold_min_m0", cfg.get("max_hold_min", 60))
    target_r = cfg["target_r"]
    for _, t in trades.iterrows():
        r = simulate_bar_path(
            m.m1_hi, m.m1_lo, m.m1_cl,
            int(t["entry_i"]), t["direction"], float(t["entry_price"]),
            stop_atr, m.m1_atr, target_r, hold,
        )
        cr = NQ.cost_r(float(t["entry_price"]), r.risk_pts, 1.0)
        rows.append({
            "trade_id": t["trade_id"],
            "direction": t["direction"],
            "entry_i": r.entry_i,
            "entry_price": r.entry_price,
            "stop": r.stop,
            "target": r.target,
            "exit_i": r.exit_i,
            "exit_price": r.exit_price,
            "exit_reason": r.exit_reason,
            "gross_R": r.gross_r,
            "cost_R": cr,
            "net_R": r.gross_r - cr,
            "MFE_R": r.mfe_r,
            "MAE_R": r.mae_r,
            "atr": r.atr,
            "risk_pts": r.risk_pts,
            "collision_bar": r.collision_bar,
            "duration_min": r.exit_i - r.entry_i,
        })
    return pd.DataFrame(rows)
