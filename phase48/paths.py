"""Trade path diagnostics for M0 control."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase45.execution.data_1m import load_market_1m

from .entries import enrich_entry_row, entry_index, load_frozen_entries
from .simulate_mgmt import MgmtSpec, simulate_managed


def build_trade_paths(entries: pd.DataFrame | None = None, market: pd.DataFrame | None = None) -> pd.DataFrame:
    mkt = market if market is not None else load_market_1m()
    ent = entries if entries is not None else load_frozen_entries()
    rows = []
    spec = MgmtSpec(name="M0")
    for _, raw in ent.iterrows():
        row = enrich_entry_row(raw, mkt)
        ei = int(row["entry_i"])
        if ei < 0 or ei >= len(mkt):
            continue
        sim = simulate_managed(
            mkt, ei, float(row["entry_price"]), float(row["initial_stop"]), float(row["initial_target"]),
            row["direction"], row["signal_type"], spec,
        )
        risk = abs(float(row["entry_price"]) - float(row["initial_stop"])) or 1e-9
        hi = mkt["high"].astype(float).values
        lo = mkt["low"].astype(float).values
        d = 1 if str(row["direction"]).lower() == "long" else -1
        max_giveback = 0.0
        peak = 0.0
        exit_i = sim.get("exit_i", entry_index(mkt, sim["exit_timestamp"]))
        hold = sim.get("hold_bars", int(exit_i) - ei if exit_i >= 0 else 0)
        for j in range(ei + 1, min(int(exit_i) + 1, len(mkt))):
            if d == 1:
                r_now = (hi[j] - float(row["entry_price"])) / risk
            else:
                r_now = (float(row["entry_price"]) - lo[j]) / risk
            peak = max(peak, r_now)
            max_giveback = max(max_giveback, peak - r_now)
        reached_1r_then_neg = bool(sim["MFE_R"] >= 1.0 and sim["net_R"] < 0)
        reached_2r_gave_1 = bool(sim["MFE_R"] >= 2.0 and (sim["MFE_R"] - sim["net_R"]) > 1.0)
        rows.append({
            "signal_id": row["signal_id"],
            "entry_timestamp": row["entry_timestamp"],
            "direction": row["direction"],
            "phase44_class": row.get("confidence"),
            "setup_type": row.get("signal_type"),
            "walk_forward_fold": row.get("fold"),
            "entry_price": row["entry_price"],
            "initial_stop": row["initial_stop"],
            "initial_target": row["initial_target"],
            "initial_risk_points": risk,
            "atr_entry": row.get("atr_entry"),
            "mfe_r": sim["MFE_R"],
            "mae_r": sim["MAE_R"],
            "time_to_0_5r": sim.get("bars_to_plus_0.5r"),
            "time_to_1r": sim.get("bars_to_plus_1r"),
            "time_to_1_5r": sim.get("bars_to_plus_1.5r"),
            "time_to_2r": sim.get("bars_to_plus_2r"),
            "time_to_mfe": np.nan,
            "max_giveback": max_giveback,
            "control_exit_timestamp": sim["exit_timestamp"],
            "control_exit_price": sim.get("exit_price"),
            "control_exit_r": sim["net_R"],
            "control_exit_type": sim["exit_type"],
            "hold_minutes": hold,
            "reached_1r_then_negative": int(reached_1r_then_neg),
            "reached_2r_gave_back_1r": int(reached_2r_gave_1),
        })
    return pd.DataFrame(rows)
