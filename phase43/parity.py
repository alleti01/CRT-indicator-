"""Phase 40 baseline parity for Phase 43."""

from __future__ import annotations

import json

import pandas as pd

from phase31.metrics import performance
from phase36.data import load_replay_market_15m
from phase36.outcomes import score_outcomes
from phase40.filter import apply_filter
from phase40.metrics import enrich_net, segment_results, yearly_results

from .config import (
    EXP_AVGR,
    EXP_L,
    EXP_N,
    EXP_OOS_AVGR,
    EXP_OOS_N,
    EXP_PF,
    EXP_RL,
    EXP_RS,
    EXP_S,
    EXP_TOTAL,
    P40_FILTERED,
    P40_MANIFEST,
)


def load_frozen_signals() -> pd.DataFrame:
    df = pd.read_csv(P40_FILTERED)
    df = df.loc[df["accepted"]].copy()
    df["marker_bar_timestamp"] = pd.to_datetime(df["marker_bar_timestamp"], utc=True)
    return df


def verify_phase40_parity(signals: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    counts = {
        "L": int((signals["signal_type"] == "L").sum()),
        "S": int((signals["signal_type"] == "S").sum()),
        "RL": int((signals["signal_type"] == "RL").sum()),
        "RS": int((signals["signal_type"] == "RS").sum()),
        "total": int(len(signals)),
    }
    parity_ok = (
        counts["L"] == EXP_L
        and counts["S"] == EXP_S
        and counts["RL"] == EXP_RL
        and counts["RS"] == EXP_RS
        and counts["total"] == EXP_TOTAL
    )
    perf = performance(scored, col="net_R")
    avgr_ok = abs(perf.get("AvgR", 0) - EXP_AVGR) <= 0.015
    pf_ok = abs(perf.get("PF", 0) - EXP_PF) <= 0.08
    rows = [
        {"metric": "parity_pass", "value": float(parity_ok and avgr_ok and pf_ok)},
        {"metric": "L", "value": counts["L"]},
        {"metric": "S", "value": counts["S"]},
        {"metric": "RL", "value": counts["RL"]},
        {"metric": "RS", "value": counts["RS"]},
        {"metric": "total", "value": counts["total"]},
        {"metric": "AvgR", "value": perf.get("AvgR", 0)},
        {"metric": "PF", "value": perf.get("PF", 0)},
        {"metric": "N", "value": perf.get("N", 0)},
    ]
    return pd.DataFrame(rows)


def build_parity_tables(scored: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    seg = segment_results(scored, col="net_R")
    yearly = yearly_results(scored, col="net_R")
    return seg, yearly


def cross_check_filter_rebuild(market: pd.DataFrame) -> bool:
    """Optional: re-apply Phase 40 filter and confirm identical acceptance."""
    from phase40.config import P37_SIGNAL_MAP

    raw = pd.read_csv(P37_SIGNAL_MAP)
    raw["marker_bar_timestamp"] = pd.to_datetime(raw["marker_bar_timestamp"], utc=True)
    _all, accepted, _rej = apply_filter(raw, market)
    frozen = load_frozen_signals()
    return len(accepted) == len(frozen) == EXP_TOTAL
