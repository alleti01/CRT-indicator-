"""Alignment matcher tests. Synthetic bars only — not market data."""
from __future__ import annotations

import pandas as pd

from cdx_research.python.align_labels import align_labels, medium_gate
from cdx_research.python.tzutil import ET, UTC


def _labels():
    return pd.DataFrame(
        [
            {
                "screenshot_id": "s06",
                "date": "2026-09-17",
                "signal_time_et": "2026-09-17 14:38:00",
                "direction": "LONG",
                "timestamp_confidence": "MEDIUM",
                "approximate_price": 29700.0,
                "outcome_visible": "yes",
                "visible_R": "",
                "notes": "",
            },
            {
                "screenshot_id": "s07",
                "date": "2026-09-17",
                "signal_time_et": "2026-09-17 11:48:00",
                "direction": "SHORT",
                "timestamp_confidence": "MEDIUM",
                "approximate_price": 29745.0,
                "outcome_visible": "yes",
                "visible_R": "",
                "notes": "",
            },
            {
                "screenshot_id": "s02",
                "date": "2026-09-21",
                "signal_time_et": "2026-09-21 06:33:00",
                "direction": "SHORT",
                "timestamp_confidence": "LOW",
                "approximate_price": 30220.0,
                "outcome_visible": "yes",
                "visible_R": "",
                "notes": "",
            },
        ]
    )


def _series(times_et, tz=ET):
    idx = pd.DatetimeIndex([pd.Timestamp(t, tz=ET).tz_convert(tz) for t in times_et])
    return pd.DataFrame(
        {
            "open": [1.0] * len(idx),
            "high": [2.0] * len(idx),
            "low": [0.5] * len(idx),
            "close": [1.5] * len(idx),
            "volume": [10] * len(idx),
        },
        index=idx,
    )


def test_exact_and_low_context():
    m1 = _series(
        [
            "2026-09-17 14:38:00",
            "2026-09-17 11:48:00",
            "2026-09-21 06:33:00",
        ]
    )
    audit = align_labels(_labels(), m1, source="TEST")
    med = audit[audit["confidence"] == "MEDIUM"]
    assert list(med["match_status"]) == ["EXACT", "EXACT"]
    low = audit[audit["confidence"] == "LOW"]
    assert list(low["match_status"]) == ["CONTEXT_ONLY"]
    gate = medium_gate(audit)
    assert gate["exact"] == 2
    assert gate["gate_pass"] is False  # only 2 of 2 in this fixture; real gate is 7/10


def test_plus_minus_one():
    m1 = _series(["2026-09-17 14:37:00", "2026-09-17 11:48:00"])
    audit = align_labels(_labels().iloc[:2], m1, source="TEST")
    assert audit.iloc[0]["match_status"] == "PLUS_MINUS_1"
    assert int(audit.iloc[0]["delta_minutes"]) == -1
    assert audit.iloc[1]["match_status"] == "EXACT"


def test_ambiguous_both_neighbors():
    m1 = _series(["2026-09-17 14:37:00", "2026-09-17 14:39:00"])
    audit = align_labels(_labels().iloc[:1], m1, source="TEST")
    assert audit.iloc[0]["match_status"] == "AMBIGUOUS"


def test_empty_unmatched():
    empty = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    empty.index = pd.DatetimeIndex([], tz=UTC)
    audit = align_labels(_labels(), empty, source="NONE")
    assert set(audit["match_status"]) == {"UNMATCHED"}


def test_chicago_index_matches_et_label():
    m1 = _series(["2026-09-17 14:38:00"], tz=pd.DatetimeIndex([pd.Timestamp("2026-09-17 14:38:00", tz=ET)]).tz_convert("America/Chicago").tz)
    # rebuild explicitly in CT
    ts_et = pd.Timestamp("2026-09-17 14:38:00", tz=ET)
    m1 = pd.DataFrame(
        {"open": [1], "high": [2], "low": [0.5], "close": [1.5], "volume": [10]},
        index=pd.DatetimeIndex([ts_et.tz_convert("America/Chicago")]),
    )
    audit = align_labels(_labels().iloc[:1], m1, source="TEST")
    assert audit.iloc[0]["match_status"] == "EXACT"


if __name__ == "__main__":
    test_exact_and_low_context()
    test_plus_minus_one()
    test_ambiguous_both_neighbors()
    test_empty_unmatched()
    test_chicago_index_matches_et_label()
    print("ALIGN_TESTS_PASS")
