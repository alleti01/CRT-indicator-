"""Phase54 episode consolidation tests."""

from __future__ import annotations

import pandas as pd
import pytest

from phase54.research.consolidate import consolidate_opposite_reset, consolidate_time


def _ev(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_time_consolidation_suppresses_same_dir():
    ev = _ev(
        [
            {"timestamp_ct": pd.Timestamp("2024-01-02 10:00", tz="America/Chicago"), "direction": "LONG", "net_R": 1.0, "event_id": "a"},
            {"timestamp_ct": pd.Timestamp("2024-01-02 10:02", tz="America/Chicago"), "direction": "LONG", "net_R": 2.0, "event_id": "b"},
            {"timestamp_ct": pd.Timestamp("2024-01-02 10:20", tz="America/Chicago"), "direction": "LONG", "net_R": 0.5, "event_id": "c"},
        ]
    )
    ret, sup = consolidate_time(ev, 10)
    assert len(ret) == 2
    assert len(sup) == 1


def test_opposite_reset_allows_flip():
    ev = _ev(
        [
            {"timestamp_ct": pd.Timestamp("2024-01-02 10:00", tz="America/Chicago"), "direction": "LONG", "net_R": 1.0, "event_id": "a"},
            {"timestamp_ct": pd.Timestamp("2024-01-02 10:05", tz="America/Chicago"), "direction": "SHORT", "net_R": 0.5, "event_id": "b"},
        ]
    )
    ret, sup = consolidate_opposite_reset(ev)
    assert len(ret) == 2


def test_first_event_retained_not_later():
    ev = _ev(
        [
            {"timestamp_ct": pd.Timestamp("2024-01-02 10:00", tz="America/Chicago"), "direction": "LONG", "net_R": 1.0, "event_id": "first"},
            {"timestamp_ct": pd.Timestamp("2024-01-02 10:01", tz="America/Chicago"), "direction": "LONG", "net_R": 3.0, "event_id": "later"},
        ]
    )
    ret, sup = consolidate_time(ev, 15)
    assert ret.iloc[0]["event_id"] == "first"
