"""Tests for Phase 24 entry precision."""

from __future__ import annotations

import pandas as pd
import pytest

from phase24.analyze_entry_precision import performance_table, winner_loser_analysis
from phase24.build_entry_dataset import _first_passage_labels, load_baseline_trades


def test_first_passage_good_before_bad():
    labels = _first_passage_labels("Long", 100.0, 10.0, highs=[101, 106], lows=[99.5, 99])
    assert labels["good_entry"] is True
    assert labels["bad_entry"] is False


def test_first_passage_bad_before_good():
    labels = _first_passage_labels("Long", 100.0, 10.0, highs=[100.5, 106], lows=[94, 99])
    assert labels["bad_entry"] is True


def test_baseline_trades_load():
    trades = load_baseline_trades()
    assert len(trades) > 10000
    assert "entry_timestamp" in trades.columns


def test_performance_table():
    df = pd.DataFrame({"result_R": [1.0, -0.5, 0.5, -1.0]})
    perf = performance_table(df)
    assert perf["N"] == 4
    assert perf["AvgR"] == 0.0
