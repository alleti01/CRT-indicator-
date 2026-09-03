"""Phase 50 Pine parity tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from phase45.execution.confirm import confirm_b1
from phase45.execution.data_1m import load_market_1m
from phase45.execution.signals import load_phase44_accepted, verify_phase44_parity
from phase48.entries import load_frozen_entries
from phase48.parity import verify_entry_parity
from phase49.parity import verify_m0_parity
from phase50.config import FROZEN_B1_WINDOW_MIN, PRICE_TOLERANCE, RESULTS, TICK_SIZE
from phase50.export_reference import build_reference_signals, build_sample_reference
from phase50.tools.compare_pine_python import compare_events, parity_summary


def test_phase44_historical_parity():
    p44, _ = verify_phase44_parity(load_phase44_accepted())
    assert bool(p44.loc[p44["metric"] == "parity_pass", "value"].iloc[0])


def test_phase45_b1_historical_parity():
    _, _, ok = verify_entry_parity()
    assert ok


def test_m0_historical_parity():
    _, ok = verify_m0_parity()
    assert ok


def test_python_reference_export():
    df = build_reference_signals()
    assert len(df) > 1000
    assert "entry_timestamp" in df.columns
    assert (df["b1_window"] == FROZEN_B1_WINDOW_MIN).all()


def test_b1_ten_minute_boundary():
    market = load_market_1m()
    pos = {ts: i for i, ts in enumerate(market.index)}
    sigs = load_phase44_accepted().head(5)
    for _, sig in sigs.iterrows():
        act = pd.Timestamp(sig["actionable_timestamp"]).tz_convert(market.index.tz)
        end = act + pd.Timedelta(minutes=FROZEN_B1_WINDOW_MIN)
        fill = confirm_b1(market, pos, act, FROZEN_B1_WINDOW_MIN, sig["direction"])
        if fill.filled:
            assert fill.entry_time >= act
            assert fill.entry_time <= end
            assert fill.delay_min <= FROZEN_B1_WINDOW_MIN


def test_timestamp_alignment_actionable():
    ref = build_reference_signals().head(20)
    for _, r in ref.iterrows():
        delta = (pd.Timestamp(r["entry_timestamp"]) - pd.Timestamp(r["actionable_timestamp"])).total_seconds() / 60
        assert delta >= 0
        assert delta <= FROZEN_B1_WINDOW_MIN + 0.01


def test_timezone_chicago():
    ref = build_reference_signals().head(1)
    if ref.empty:
        pytest.skip("empty ref")
    ts = pd.Timestamp(ref.iloc[0]["entry_timestamp"])
    assert str(ts.tz) in ("America/Chicago", "US/Central")


def test_duplicate_event_detection():
    ref = build_reference_signals()
    assert not ref["signal_id"].duplicated().any()


def test_compare_parser_missing():
    py = build_sample_reference(build_reference_signals(), min_per=2)
    pine = pd.DataFrame()
    cmp_df = compare_events(py, pine)
    assert (cmp_df["status"] == "MISSING_IN_PINE").all()


def test_compare_parser_extra():
    py = pd.DataFrame()
    pine = pd.DataFrame([{"signal_id": "X", "entry_timestamp": pd.Timestamp("2020-01-01 10:00:00", tz="America/Chicago"), "direction": "Long"}])
    cmp_df = compare_events(py, pine)
    assert (cmp_df["status"] == "EXTRA_IN_PINE").any()


def test_price_tolerance():
    assert PRICE_TOLERANCE == TICK_SIZE


def test_direction_mismatch_detection():
    py = pd.DataFrame([{"signal_id": "A", "entry_timestamp": "2020-01-01 10:00:00-06:00", "direction": "Long", "phase44_class": "A", "setup_type": "L", "entry_price": 100.0, "stop": 99.0, "target": 103.0, "exit_type": "TARGET"}])
    pine = pd.DataFrame([{"signal_id": "A", "entry_timestamp": "2020-01-01 10:00:00-06:00", "direction": "Short", "phase44_class": "A", "setup_type": "L", "entry_price": 100.0, "stop": 99.0, "target": 103.0, "exit_type": "TARGET"}])
    cmp_df = compare_events(py, pine)
    assert cmp_df.iloc[0]["status"] == "DIRECTION_MISMATCH"


def test_class_mismatch_detection():
    py = pd.DataFrame([{"signal_id": "A", "entry_timestamp": "2020-01-01 10:00:00-06:00", "direction": "Long", "phase44_class": "A+", "setup_type": "L", "entry_price": 100.0, "stop": 99.0, "target": 103.0, "exit_type": "TARGET"}])
    pine = pd.DataFrame([{"signal_id": "A", "entry_timestamp": "2020-01-01 10:00:00-06:00", "direction": "Long", "phase44_class": "B", "setup_type": "L", "entry_price": 100.0, "stop": 99.0, "target": 103.0, "exit_type": "TARGET"}])
    assert compare_events(py, pine).iloc[0]["status"] == "CLASS_MISMATCH"


def test_entry_mismatch_detection():
    py = pd.DataFrame([{"signal_id": "A", "entry_timestamp": "2020-01-01 10:00:00-06:00", "direction": "Long", "phase44_class": "A", "setup_type": "L", "entry_price": 100.0, "stop": 99.0, "target": 103.0, "exit_type": "TARGET"}])
    pine = pd.DataFrame([{"signal_id": "A", "entry_timestamp": "2020-01-01 10:00:00-06:00", "direction": "Long", "phase44_class": "A", "setup_type": "L", "entry_price": 200.0, "stop": 99.0, "target": 103.0, "exit_type": "TARGET"}])
    assert compare_events(py, pine).iloc[0]["status"] == "ENTRY_MISMATCH"


def test_exit_mismatch_detection():
    py = pd.DataFrame([{"signal_id": "A", "entry_timestamp": "2020-01-01 10:00:00-06:00", "direction": "Long", "phase44_class": "A", "setup_type": "L", "entry_price": 100.0, "stop": 99.0, "target": 103.0, "exit_type": "STOP"}])
    pine = pd.DataFrame([{"signal_id": "A", "entry_timestamp": "2020-01-01 10:00:00-06:00", "direction": "Long", "phase44_class": "A", "setup_type": "L", "entry_price": 100.0, "stop": 99.0, "target": 103.0, "exit_type": "TARGET"}])
    assert compare_events(py, pine).iloc[0]["status"] == "EXIT_MISMATCH"


def test_pine_indicator_exists():
    assert (Path(__file__).resolve().parents[1] / "pine" / "phase50_nq_indicator.pine").exists()


def test_parity_summary():
    py = build_sample_reference(build_reference_signals(), min_per=1)
    cmp_df = compare_events(py.head(3), py.head(3))
    s = parity_summary(cmp_df)
    assert s["full_trade_parity_rate"] == 1.0


def test_frozen_entries_load():
    e = load_frozen_entries()
    assert len(e) == 1135
