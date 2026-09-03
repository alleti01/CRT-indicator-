"""Phase52 data loading and documentation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from phase36.data import load_replay_market_15m
from phase45.execution.data_1m import load_market_1m

from phase52.config import RESULTS, TIMEZONE


def load_markets() -> tuple[pd.DataFrame, pd.DataFrame]:
    m1 = load_market_1m()
    m15 = load_replay_market_15m()
    if "atr" not in m1.columns:
        from phase16.indicators import add_base_indicators
        from phase31.config import frozen_config_15m

        m1 = add_base_indicators(m1, frozen_config_15m())
    return m1, m15


def align_15m_to_1m(m1: pd.DataFrame, m15: pd.DataFrame) -> pd.DataFrame:
    """Forward-fill last completed 15M bar onto 1M index (causal)."""
    m15 = m15.reindex(m15.index.union(m1.index)).sort_index().ffill()
    return m15.reindex(m1.index, method="ffill")


def document_data(m1: pd.DataFrame, m15: pd.DataFrame) -> dict:
    doc = {
        "timezone": TIMEZONE,
        "session_convention": "RTH 0930-1600 CT for optional filters",
        "m1_first": str(m1.index.min()),
        "m1_last": str(m1.index.max()),
        "m1_bars": int(len(m1)),
        "m15_first": str(m15.index.min()),
        "m15_last": str(m15.index.max()),
        "m15_bars": int(len(m15)),
        "m1_sources": "phase45.execution.data_1m RAW_1M_PATHS (stitched)",
        "m15_sources": "phase36.data load_replay_market_15m (5m aggregated)",
        "missing_data": "dropna on OHLC; no forward fill on prices",
    }
    (RESULTS / "data_manifest.json").write_text(json.dumps(doc, indent=2) + "\n")
    return doc
