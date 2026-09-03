"""Entry stage causality tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase57.research.legs import detect_legs
from phase57.research.pullbacks import detect_pullbacks
from phase57.research.sequences import detect_sequences
from phase57.research.entry_stages import compute_entry_stages


def _trending_up(n: int = 300) -> pd.DataFrame:
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(n) * 0.3 + 0.1) + 100
    hi = prices + np.abs(np.random.randn(n)) * 0.5
    lo = prices - np.abs(np.random.randn(n)) * 0.5
    op = prices - 0.1
    cl = prices + 0.1
    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="1min", tz="America/Chicago")
    df = pd.DataFrame({"open": op, "high": hi, "low": lo, "close": cl}, index=idx)
    df["atr"] = pd.Series(hi - lo).rolling(14, min_periods=1).mean().values
    return df


def test_entry_stages_ordering():
    """E0 must be earliest; each subsequent stage at same or later bar."""
    m1 = _trending_up(300)
    legs = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    pbs = detect_pullbacks(m1, legs, min_depth_pct=0.1)
    seqs = detect_sequences(m1, legs, pbs)
    for seq in seqs[:5]:
        stages = compute_entry_stages(m1, seq)
        e0_bar = None
        for s in stages:
            if s["stage"] == "E0" and s["entry_i"] is not None:
                e0_bar = s["entry_i"]
            if s["entry_i"] is not None and e0_bar is not None:
                assert s["entry_i"] >= e0_bar, f"{s['stage']} at {s['entry_i']} before E0 at {e0_bar}"


def test_delay_bars_correct():
    m1 = _trending_up(300)
    legs = detect_legs(m1, start_i=20, min_distance_atr=0.5)
    pbs = detect_pullbacks(m1, legs, min_depth_pct=0.1)
    seqs = detect_sequences(m1, legs, pbs)
    for seq in seqs[:3]:
        stages = compute_entry_stages(m1, seq)
        e0_i = seq.setup_i
        for s in stages:
            if s["entry_i"] is not None and s["delay_bars"] is not None:
                assert s["delay_bars"] == s["entry_i"] - e0_i
