"""Baselines A–E for Phase58D."""
from __future__ import annotations

import pandas as pd

from phase58c.research.clustering import cluster_1m_opportunities, summarize_opportunities
from phase58d.research.engine import online_memory_at_signals, run_variant


def baseline_a_frozen(trades_path) -> pd.DataFrame:
    return pd.read_parquet(trades_path)


def baseline_b_first_per_opp(trades: pd.DataFrame, armed_i, structural_gap: int = 30) -> pd.DataFrame:
    """Phase58C first-signal-per-opportunity."""
    clustered = cluster_1m_opportunities(trades, armed_i, structural_gap=structural_gap)
    first = clustered.sort_values("signal_i").groupby("opportunity_id", sort=False).first().reset_index()
    return first


def baseline_cde(m, trades, cfg, variant: str, system: str):
    return run_variant(m, trades, cfg, variant, system)
