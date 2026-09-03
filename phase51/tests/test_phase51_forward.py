"""Phase51 forward validation tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PINE = ROOT / "phase51" / "pine" / "phase51_nq_live_indicator.pine"
MANIFEST = ROOT / "phase51" / "frozen_model" / "model_manifest.json"
HASH_FILE = ROOT / "phase51" / "frozen_model" / "model_hash.txt"


def _pine_text() -> str:
    return PINE.read_text(encoding="utf-8")


def _strategy_section(text: str) -> str:
    m = re.search(r"if chart1m and barstate.isconfirmed(.*?)// ═══ VISUALS", text, re.DOTALL)
    assert m, "strategy section not found"
    return m.group(1)


def test_phase51_pine_exists():
    assert PINE.exists()


def test_no_realtime_strategy_branch():
    section = _strategy_section(_pine_text())
    assert "barstate.isrealtime" not in section


def test_lookahead_off_on_security():
    text = _pine_text()
    assert "lookahead = barmerge.lookahead_off" in text


def test_canonical_entry_events():
    text = _pine_text()
    assert "p51LongEntryEvent" in text
    assert 'plotshape(p51LongEntryEvent' in text
    assert 'alertcondition(p51LongEntryEvent' in text


def test_forward_csv_headers():
    for name, cols in [
        ("phase44_signals.csv", "signal_id,phase44_time_ct,direction,class,setup,b1_window_start,b1_window_end"),
        ("b1_events.csv", "signal_id,confirmed,b1_time_ct,delay_minutes,direction"),
        ("trades.csv", "signal_id,direction,phase44_time_ct,b1_time_ct,entry_time_ct"),
    ]:
        path = ROOT / "phase51" / "forward" / name
        header = path.read_text().splitlines()[0]
        assert header.startswith(cols.split(",")[0])
        for c in cols.split(",")[1:3]:
            assert c in header


def test_frozen_manifest():
    assert MANIFEST.exists()
    data = json.loads(MANIFEST.read_text())
    assert data.get("b1_window_min") == 10
    assert data.get("model_hash")
    assert HASH_FILE.read_text().strip() == data["model_hash"]


def test_model_hash_embedded_in_pine():
    manifest = json.loads(MANIFEST.read_text())
    text = _pine_text()
    assert manifest["model_hash"] in text
    assert manifest["model_hash"] != "PLACEHOLDER"


def test_phase50_unchanged():
    p50 = ROOT / "phase50" / "pine" / "phase50_nq_indicator.pine"
    assert p50.exists()
    assert "Phase51" not in p50.read_text()


def test_no_barstate_realtime_anywhere_in_execution():
    text = _pine_text()
    # Phase44 bundle uses barstate.isconfirmed only
    assert "barstate.isrealtime" not in text
