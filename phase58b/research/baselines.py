"""Run all four baseline systems A/B/C/D."""
from __future__ import annotations

import pandas as pd

from phase58.research.precompute import build_market_arrays
from phase58.research.trader_engine import TraderEngine
from phase58b.research.execution_1m import execute_all_variants, execute_1m
from phase58b.research.precompute import MTFArrays, build_mtf_arrays
from phase58b.research.simulation import simulate_trades
from phase58b.research.trader_5m import FiveMTraderEngine


def run_system_a(cfg58: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Phase58 original 1M trader."""
    m1 = build_market_arrays(swing=cfg58.get("swing_period", 5))
    eng = TraderEngine(m1, cfg58)
    eng.run()
    return eng.results()


def run_system_b(m: MTFArrays, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Phase58 logic on 5M without 15M."""
    eng = FiveMTraderEngine(m, cfg, use_15m=False)
    eng.run()
    return eng.results()


def run_system_c(m: MTFArrays, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """15M + 5M, execute at next 5M open (E5)."""
    eng = FiveMTraderEngine(m, cfg, use_15m=True)
    eng.run()
    return eng.results()


def run_system_d(m: MTFArrays, cfg: dict, variant: str = "X1") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """15M + 5M + 1M execution."""
    dec, setups, takes = run_system_c(m, cfg)
    if takes.empty:
        return dec, setups, takes, pd.DataFrame()
    execs = execute_all_variants(m, takes, cfg)
    execs = execs.loc[execs["variant"] == variant].copy()
    # merge 15m fields from takes
    execs = execs.merge(takes[["setup_id", "15m_state", "15m_strength", "signal_m1_i"]], on="setup_id", how="left")
    for i, row in execs.iterrows():
        ei = int(row["entry_i"])
        if ei >= 0 and ei < m.m1_n:
            execs.at[i, "entry_ts"] = str(m.m1_idx[ei])
    return dec, setups, takes, execs


def trades_from_takes_e5(m: MTFArrays, takes: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Build E5 execution records from 5M takes."""
    rows = []
    for _, t in takes.iterrows():
        j = int(t["take_j"])
        e5_i = int(m.m5_close_m1_i[j])
        rows.append({
            "setup_id": t["setup_id"],
            "direction": t["direction"],
            "take_j": j,
            "take_price": t["take_price"],
            "take_ts": t["take_ts"],
            "tag": t.get("tag", "CONTINUATION"),
            "variant": "E5",
            "entry_i": e5_i,
            "entry_price": m.m1_op[e5_i],
            "delay_bars_1m": 0,
            "price_improvement_atr": 0,
            "entry_deterioration_atr": t.get("entry_deterioration_atr", 0),
            "15m_state": t.get("15m_state", ""),
            "15m_strength": t.get("15m_strength", 0),
        })
    return pd.DataFrame(rows)
