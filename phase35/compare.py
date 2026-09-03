"""Compare Phase 35 discovery against Phase 31/33 benchmarks."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from phase32.parity import extract_frozen_signals
from phase33.displacements import precompute_opposite_bos, scan_displacements
from phase33.failure import build_failure_events, failure_signals
from phase33.entries import simulate_all_reversal
from phase31.data import load_market_15m
from phase31.dedupe import dedupe_signals
from phase31.metrics import simulate_all
from phase29.simulator import SimConfig
from phase33.config import WF_FAILURE_DEFS

from .config import PHASE31_WF_TRADES, PHASE33_WF_TRADES


def _load_phase31_entries(market: pd.DataFrame) -> pd.DataFrame:
    sig = extract_frozen_signals(market)
    cfg = SimConfig(entry_model="BOS_RETEST", stop_atr=0.75, target_r=3.0, max_bars=4, management="FIXED")
    sim = simulate_all(sig, market, cfg)
    filled = sim.loc[sim.filled].copy()
    filled["architecture"] = "MOMENTUM_DISPLACEMENT"
    filled["signal_type"] = np.where(filled["direction"].str.lower() == "long", "CONTINUATION_LONG", "CONTINUATION_SHORT")
    return filled


def _load_phase33_entries(market: pd.DataFrame) -> pd.DataFrame:
    bos, _ = precompute_opposite_bos(market)
    disp = scan_displacements(market)
    failures = build_failure_events(disp, market, bos)
    sig = dedupe_signals(failure_signals(failures, "A_MID_4"), market)
    cfg = {
        "entry_model": "RECLAIM_RETEST",
        "stop_atr": 0.75,
        "target_r": 2.5,
        "max_bars": 3,
        "hold_minutes": 45,
        "management": "FIXED",
    }
    sim = simulate_all_reversal(sig, market, cfg)
    filled = sim.loc[sim.filled].copy()
    filled["architecture"] = "DISPLACEMENT_FAILURE_REVERSAL"
    filled["signal_type"] = np.where(filled["direction"].str.lower() == "long", "REVERSAL_LONG", "REVERSAL_SHORT")
    return filled


def capture_rate(
    opportunities: pd.DataFrame,
    entries: pd.DataFrame,
    *,
    quality: str = "STRONG",
    direction: str | None = None,
) -> Dict[str, float]:
    """Fraction of historical opportunity bars matched by system entry timestamps."""
    opps = opportunities.loc[opportunities["quality"] == quality].copy()
    if direction is not None:
        opps = opps.loc[opps["direction"].str.lower() == direction.lower()]
    if opps.empty or entries.empty:
        return {"N_opportunities": 0, "N_captured": 0, "capture_pct": 0.0}

    entry_ts = pd.to_datetime(entries["entry_timestamp"])
    captured = 0
    for ts in opps["timestamp"]:
        if (entry_ts == ts).any():
            captured += 1
    return {
        "N_opportunities": int(len(opps)),
        "N_captured": int(captured),
        "capture_pct": float(captured / len(opps)) if len(opps) else 0.0,
    }


def compare_systems(
    opportunities: pd.DataFrame,
    phase35_trades: pd.DataFrame,
    market: pd.DataFrame,
) -> pd.DataFrame:
    p31 = _load_phase31_entries(market)
    p33 = _load_phase33_entries(market)

    rows = []
    for name, entries in (
        ("Phase31_MOMENTUM_DISPLACEMENT", p31),
        ("Phase33_REVERSAL", p33),
        ("Phase35_DISCOVERED", phase35_trades),
    ):
        for quality in ("STRONG", "GOOD"):
            for direction in ("Long", "Short"):
                opps = opportunities.loc[
                    (opportunities["quality"] == quality) & (opportunities["direction"] == direction)
                ]
                sub = entries.loc[entries["direction"].str.lower() == direction.lower()] if not entries.empty else entries
                cap = capture_rate(opportunities, sub, quality=quality, direction=direction)
                rows.append(
                    {
                        "system": name,
                        "direction": direction,
                        "quality_tier": quality,
                        "opportunities": int(len(opps)),
                        "system_entries": int(len(sub)),
                        "captured_strong_opportunities": cap.get("N_captured", 0),
                        "capture_pct": cap.get("capture_pct", 0.0),
                    }
                )
    return pd.DataFrame(rows)


def overlap_summary(p31: pd.DataFrame, p33: pd.DataFrame, p35: pd.DataFrame) -> Dict[str, int]:
    def ts_set(df):
        return set(pd.to_datetime(df["entry_timestamp"])) if not df.empty else set()

    s31, s33, s35 = ts_set(p31), ts_set(p33), ts_set(p35)
    return {
        "p31_only": len(s31 - s33 - s35),
        "p33_only": len(s33 - s31 - s35),
        "p35_only": len(s35 - s31 - s33),
        "all_three": len(s31 & s33 & s35),
        "p31_p33": len(s31 & s33),
        "p35_catches_beyond_p31_p33": len(s35 - s31 - s33),
    }
