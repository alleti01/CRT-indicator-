"""Phase79 one-position simulation on frozen entries."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ
from phase69.python.entry_freeze import config_hash, executions, load_frozen_entries
from phase71.python.canonical_trader import TraderConfig, run_one_position
from phase79.python.atm_walk import ATMParams, counterfactual_killed_winner_path, walk_atm_a


def run_baseline_one_position(execs: pd.DataFrame, m) -> tuple[pd.DataFrame, dict]:
    cfg = TraderConfig(enable_t5=False, max_hold=60, stop_atr=1.0, target_r=2.5)
    trades, _, skipped = run_one_position(execs, m, cfg, getattr(m, "ts", None))
    trades = trades.rename(columns={"hold_minutes": "hold_minutes"})
    trades["model"] = "ATM_BASELINE"
    return trades, skipped


def run_atm_on_entries(execs: pd.DataFrame, m, params: ATMParams | None = None) -> pd.DataFrame:
    """Run ATM-A on a fixed entry list (no re-filtering — preserves baseline entry set)."""
    params = params or ATMParams()
    rows = []
    for _, ex in execs.sort_values("entry_ts").iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        atr = float(ex["atr_entry"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        rec = walk_atm_a(
            m.hi, m.lo, m.cl, m.op,
            entry_i=ei,
            direction=ex["direction"],
            entry_price=float(ex["entry_price"]),
            atr=atr,
            params=params,
            n=m.n,
        )
        rec["trade_id"] = ex["trade_id"]
        rec["direction"] = ex["direction"]
        rec["entry_i"] = ei
        rec["entry_ts"] = ex.get("entry_ts")
        rec["entry_price"] = float(ex["entry_price"])
        rec["initial_atr"] = atr
        rec["model"] = "ATM-A"
        rows.append(rec)
    return pd.DataFrame(rows)


def run_atm_one_position(execs: pd.DataFrame, m, params: ATMParams | None = None) -> tuple[pd.DataFrame, dict]:
    """Legacy one-position ATM (management-dependent entry filter — do not use for paired compare)."""
    params = params or ATMParams()
    execs = execs.sort_values("entry_ts").reset_index(drop=True)
    rows = []
    skipped = {"N": 0, "LONG": 0, "SHORT": 0}
    active_until = -1
    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65 or ei <= active_until:
            skipped["N"] += 1
            skipped[ex["direction"]] = skipped.get(ex["direction"], 0) + 1
            continue
        atr = float(ex["atr_entry"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        rec = walk_atm_a(
            m.hi, m.lo, m.cl, m.op,
            entry_i=ei,
            direction=ex["direction"],
            entry_price=float(ex["entry_price"]),
            atr=atr,
            params=params,
            n=m.n,
        )
        rec["trade_id"] = ex["trade_id"]
        rec["direction"] = ex["direction"]
        rec["entry_i"] = ei
        rec["entry_ts"] = ex.get("entry_ts")
        rec["entry_price"] = float(ex["entry_price"])
        rec["initial_atr"] = atr
        rec["model"] = "ATM-A"
        rows.append(rec)
        active_until = int(rec["exit_i"])
    return pd.DataFrame(rows), skipped


def verify_baseline_reproduction(execs: pd.DataFrame, m, trades: pd.DataFrame) -> tuple[bool, list[str]]:
    from phase71.python.canonical_trader import run_independent, run_one_position

    errors: list[str] = []
    cfg = TraderConfig(enable_t5=False)
    indep, _, _ = run_independent(execs, m, cfg)
    expected_avg = 0.01599203459208266
    actual_avg = float(indep["net_r"].mean())
    if abs(actual_avg - expected_avg) > 0.0005:
        errors.append(f"independent M0 AvgR: expected {expected_avg:.6f} got {actual_avg:.6f}")
    if len(indep) != 36174:
        errors.append(f"independent M0 N: expected 36174 got {len(indep)}")

    trades2, _, skipped2 = run_one_position(execs, m, cfg)
    if len(trades2) != len(trades):
        errors.append(f"baseline non-deterministic N: {len(trades)} vs {len(trades2)}")
    merged = trades.merge(trades2, on="trade_id", suffixes=("_a", "_b"))
    if not np.allclose(merged["net_r_a"], merged["net_r_b"], rtol=0, atol=1e-9):
        errors.append("baseline non-deterministic net_r")
    return len(errors) == 0, errors
