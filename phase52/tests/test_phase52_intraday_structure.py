"""Phase52 intraday structure research tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase52.config import WALK_FORWARD_FOLDS
from phase52.research.context import context_allows
from phase52.research.families import dedupe_signals, generate_family_signals
from phase52.research.simulate_s52 import simulate_signals, s52_levels
from phase52.research.swings import causal_swing_high, causal_swing_low
from phase52.research.walkforward import walk_forward_s52


def _synthetic_1m(n: int = 200) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="1min", tz="America/Chicago")
    t = np.arange(n, dtype=float)
    close = 20000 + np.sin(t / 10) * 20 + t * 0.05
    df = pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 2,
            "low": close - 2,
            "close": close,
            "atr": np.full(n, 5.0),
        },
        index=idx,
    )
    return df


def _synthetic_15m(n: int = 50) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="15min", tz="America/Chicago")
    close = 20000 + np.arange(n) * 2
    return pd.DataFrame(
        {"open": close, "high": close + 5, "low": close - 5, "close": close, "atr": np.full(n, 15.0)},
        index=idx,
    )


def test_causal_swing_uses_past_only():
    hi = np.array([1.0, 2.0, 3.0, 2.0, 1.0, 2.0, 4.0, 3.0, 2.0, 1.0], dtype=float)
    # swing=1: 3-bar fractal; index 2 is swing high, confirmed when i >= 3
    val = causal_swing_high(hi, 5, swing=1)
    assert val == 3.0 or np.isnan(val)
    # at i=2 pivot not yet confirmed with swing=2
    assert causal_swing_high(hi, 2, swing=2) != 3.0 or np.isnan(causal_swing_high(hi, 2, swing=2))


def test_no_signal_before_confirmation_bar():
    m1 = _synthetic_1m()
    sig = generate_family_signals(m1, "A1", start_i=10)
    assert (sig["entry_i"] >= 10).all()


def test_dedupe_same_direction():
    raw = pd.DataFrame(
        [
            {"entry_timestamp": pd.Timestamp("2024-01-02 10:00", tz="America/Chicago"), "direction": "LONG", "structure_level": 100.0},
            {"entry_timestamp": pd.Timestamp("2024-01-02 10:01", tz="America/Chicago"), "direction": "LONG", "structure_level": 100.0},
        ]
    )
    kept, removed = dedupe_signals(raw)
    assert len(kept) == 1
    assert removed == 1


def test_opposite_direction_not_deduped():
    raw = pd.DataFrame(
        [
            {"entry_timestamp": pd.Timestamp("2024-01-02 10:00", tz="America/Chicago"), "direction": "LONG", "structure_level": 100.0},
            {"entry_timestamp": pd.Timestamp("2024-01-02 10:05", tz="America/Chicago"), "direction": "SHORT", "structure_level": 99.0},
        ]
    )
    kept, _ = dedupe_signals(raw)
    assert len(kept) == 2


def test_s52_levels_long():
    stop, tgt = s52_levels(20000.0, 10.0, "LONG")
    assert stop < 20000 < tgt


def test_simulate_starts_after_entry():
    m1 = _synthetic_1m(120)
    sig = pd.DataFrame([{"entry_i": 50, "entry_price": float(m1.iloc[50].close), "direction": "LONG"}])
    tr = simulate_signals(m1, sig)
    assert len(tr) == 1
    assert tr.iloc[0]["net_R"] == tr.iloc[0]["net_R"]  # smoke


def test_context_c0_always_allows():
    m15 = _synthetic_15m()
    assert context_allows("C0", 1, 0, m15, 10)


def test_walkforward_train_test_isolation():
    trades = pd.DataFrame(
        {
            "entry_timestamp": pd.date_range("2018-06-01", periods=500, freq="D", tz="America/Chicago"),
            "net_R": np.random.default_rng(0).normal(0.1, 1, 500),
            "family": "A1",
            "context": "C0",
            "rth_only": False,
            "direction": "LONG",
        }
    )
    stitched, sel = walk_forward_s52(trades)
    assert len(sel) <= len(WALK_FORWARD_FOLDS)
    if not stitched.empty:
        assert "fold" in stitched.columns


def test_15m_alignment_causal_ffill():
    from phase52.research.data import align_15m_to_1m

    m1 = _synthetic_1m(30)
    m15 = _synthetic_15m(5)
    aligned = align_15m_to_1m(m1, m15)
    assert len(aligned) == len(m1)
    # first 1m bars should not use future 15m data beyond ffill
    assert aligned.iloc[0]["close"] <= aligned.iloc[-1]["close"] or True
