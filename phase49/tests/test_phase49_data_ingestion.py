"""Tests for Phase 49 data ingestion and firewall."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from phase45.execution.data_1m import load_market_1m
from phase49.config import DEVELOPMENT_CUTOFF, FORWARD_START_TIMESTAMP, TIMEZONE
from phase49.data.firewall import (
    assert_development_only,
    assert_forward_only,
    assert_research_safe,
    development_cutoff_ts,
    forward_start_ts,
    is_development,
    is_forward,
    split_development_forward,
)
from phase49.data.ingest import ingest_forward_data
from phase49.data.loaders import (
    load_development_1m,
    load_forward_1m,
    load_market_1m_phase49,
    load_market_15m_phase49,
    verify_research_loaders_firewalled,
)
from phase49.data.resample import resample_1m_to_15m, verify_15m_against_1m
from phase49.frozen import compute_model_hash, load_frozen_manifest
from phase49.parity import parity_passes
from phase49.run import _append_immutable


def test_forward_rows_begin_at_or_after_forward_start():
    fwd = load_forward_1m()
    if fwd.empty:
        pytest.skip("no forward 1m data ingested yet")
    assert fwd.index.min() >= forward_start_ts()


def test_development_rows_cannot_contain_forward_timestamps():
    dev = load_development_1m()
    assert_development_only(dev)


def test_forward_data_cannot_enter_research_loaders():
    verify_research_loaders_firewalled()
    research = load_market_1m()
    start = forward_start_ts()
    assert (research.index >= start).sum() == 0


def test_no_duplicate_timestamps_in_phase49_1m():
    m1 = load_market_1m_phase49()
    assert not m1.index.duplicated().any()


def test_append_ingestion_is_idempotent():
    m1 = ingest_forward_data()
    m2 = ingest_forward_data()
    assert m1["1m"]["row_count"] == m2["1m"]["row_count"]
    assert m1["1m"]["last_timestamp"] == m2["1m"]["last_timestamp"]


def test_timezone_conversion_chicago():
    dev = load_development_1m()
    if dev.empty:
        pytest.skip("empty development 1m")
    assert str(dev.index.tz) in ("America/Chicago", "US/Central")


def test_dst_handling_bridge_data():
    bridge_path = Path("phase16/data/raw/nq_continuous_1m_postwindow_to_20260629T0000CT.csv")
    if not bridge_path.exists():
        pytest.skip("bridge file missing")
    dev = load_development_1m()
    june = dev.loc["2026-06-28":"2026-06-29"]
    if june.empty:
        pytest.skip("no bridge june rows")
    assert june.index.tz is not None


def test_1m_ohlc_validity():
    m1 = load_market_1m_phase49()
    if m1.empty:
        pytest.skip("empty 1m")
    high_floor = m1[["open", "close", "low"]].max(axis=1)
    low_ceiling = m1[["open", "close", "high"]].min(axis=1)
    assert (m1["high"] >= high_floor).all()
    assert (m1["low"] <= low_ceiling).all()


def test_15m_ohlc_validity():
    m15 = load_market_15m_phase49()
    if m15.empty:
        pytest.skip("empty 15m")
    high_floor = m15[["open", "close", "low"]].max(axis=1)
    low_ceiling = m15[["open", "close", "high"]].min(axis=1)
    assert (m15["high"] >= high_floor).all()
    assert (m15["low"] <= low_ceiling).all()


def test_15m_aggregation_matches_underlying_1m():
    fwd = load_forward_1m()
    if fwd.empty:
        pytest.skip("no forward 1m")
    bars_15 = resample_1m_to_15m(fwd)
    issues = verify_15m_against_1m(bars_15, fwd)
    assert issues == []


def test_historical_parity_unchanged():
    assert parity_passes()


def test_model_hash_unchanged():
    manifest = load_frozen_manifest()
    assert manifest.get("model_hash", "").startswith("27cf15e8")
    assert compute_model_hash() == manifest["model_hash"]


def test_phase49_reads_new_forward_rows_when_present():
    manifest = ingest_forward_data()
    m1 = load_market_1m_phase49(ingest=False)
    fwd_count = manifest["1m"]["row_count"]
    assert int((m1.index >= forward_start_ts()).sum()) == fwd_count


def test_previous_forward_logs_remain_immutable(tmp_path: Path):
    sig_path = tmp_path / "forward_signals.csv"
    pd.DataFrame({"signal_id": ["FWD-00001"], "x": [1]}).to_csv(sig_path, index=False)
    prev = pd.read_csv(sig_path)
    new = pd.DataFrame({"signal_id": ["FWD-00002"], "x": [2]})
    out = _append_immutable(prev, new, "signal_id")
    assert len(out) == 2
    assert out.loc[out["signal_id"] == "FWD-00001", "x"].iloc[0] == 1


def test_duplicate_phase49_runs_do_not_duplicate_signals():
    a = pd.DataFrame({"signal_id": ["A", "B"], "v": [1, 2]})
    b = pd.DataFrame({"signal_id": ["B", "C"], "v": [9, 3]})
    out = _append_immutable(a, b, "signal_id")
    assert len(out) == 3
    assert out.loc[out["signal_id"] == "B", "v"].iloc[0] == 2


def test_firewall_timestamp_constants():
    assert DEVELOPMENT_CUTOFF == "2026-06-28 23:45:00"
    assert FORWARD_START_TIMESTAMP == "2026-06-29 00:00:00"
    assert forward_start_ts() > development_cutoff_ts()


def test_is_development_and_is_forward():
    cutoff = development_cutoff_ts()
    start = forward_start_ts()
    assert is_development(cutoff)
    assert not is_forward(cutoff)
    assert is_forward(start)
    assert not is_development(start)


def test_split_development_forward():
    idx = pd.date_range("2026-06-28 23:40", "2026-06-29 00:05", freq="5min", tz=TIMEZONE)
    df = pd.DataFrame({"close": 1.0}, index=idx)
    dev, fwd = split_development_forward(df)
    assert dev.index.max() <= development_cutoff_ts()
    assert fwd.index.min() >= forward_start_ts()
