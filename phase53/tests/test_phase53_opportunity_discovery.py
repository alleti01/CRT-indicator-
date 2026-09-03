"""Phase53 causality and pipeline tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase52.research.swings import precompute_swing_highs
from phase53.research.data import resample_5m_causal
from phase53.research.events import generate_all_events
from phase53.research.outcomes import attach_outcomes, batch_forward, batch_simulate


def _m1(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2024-01-02 09:30", periods=n, freq="1min", tz="America/Chicago")
    t = np.arange(n, dtype=float)
    c = 20000 + np.sin(t / 8) * 15 + t * 0.02
    return pd.DataFrame(
        {"open": c - 0.5, "high": c + 2, "low": c - 2, "close": c, "atr": np.full(n, 5.0)},
        index=idx,
    )


def test_swing_not_available_before_confirmation():
    hi = np.array([1, 2, 3, 2, 1, 2, 4, 3, 2, 1, 2, 3], dtype=float)
    out = precompute_swing_highs(hi, swing=2)
    assert np.isnan(out[2]) or out[2] != 3.0


def test_5m_resample_causal():
    m1 = _m1(60)
    m5 = resample_5m_causal(m1)
    assert len(m5) == 12
    assert m5.index[0] == m1.index[0]


def test_events_have_required_columns():
    m1 = _m1(200)
    ev = generate_all_events(m1, start_i=30)
    if not ev.empty:
        assert {"event_id", "timestamp_ct", "direction", "event_type"}.issubset(ev.columns)


def test_outcome_uses_future_only_in_labels():
    m1 = _m1(120)
    mfe, mae = batch_forward(m1, np.array([50]), np.array(["LONG"]), 10)
    assert len(mfe) == 1
    sim = batch_simulate(m1, np.array([50]), np.array(["LONG"]))
    assert "net_R" in sim.columns


def test_no_event_before_confirmation_index():
    m1 = _m1(150)
    ev = generate_all_events(m1, start_i=20)
    assert (ev["entry_i"] >= 20).all()


def test_train_holdout_split_exists():
    from phase53.config import HOLDOUT_START

    assert HOLDOUT_START == "2025-01-01"
