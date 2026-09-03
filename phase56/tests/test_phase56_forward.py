"""Phase56 forward validation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from phase55.implementation.s54_episodes import S54EpisodeState
from phase56.config import FROZEN, FORWARD_START_TIMESTAMP_CT, MODEL_HASH
from phase56.forward.model_guard import verify_model_hash
from phase56.forward.scoring import d10_pass, load_score_spec


def test_model_hash_frozen():
    ok, h = verify_model_hash()
    assert ok
    assert h == MODEL_HASH
    assert (FROZEN / "phase55_model_hash.txt").read_text().strip() == MODEL_HASH


def test_forward_manifest():
    m = json.loads((FROZEN / "phase56_forward_manifest.json").read_text())
    assert m["forward_start_timestamp_ct"] == FORWARD_START_TIMESTAMP_CT
    assert m["model_hash"] == MODEL_HASH
    assert m["paper_only"] is True


def test_d10_frozen_threshold():
    spec = load_score_spec()
    thr = spec["d10_min_score_inclusive"]
    assert d10_pass(thr)
    assert not d10_pass(thr - 0.001)


def test_episode_30m_boundary():
    st = S54EpisodeState(window_min=30)
    t0 = pd.Timestamp("2025-01-06 10:00:00", tz="America/Chicago")
    st.process(t0, "LONG")
    assert st.process(t0 + pd.Timedelta(minutes=30), "LONG")["suppressed"]
    assert st.process(t0 + pd.Timedelta(minutes=31), "LONG")["s54_entry"]


def test_opposite_direction_independent():
    st = S54EpisodeState(window_min=30)
    t0 = pd.Timestamp("2025-01-06 10:00:00", tz="America/Chicago")
    st.process(t0, "LONG")
    assert st.process(t0 + pd.Timedelta(minutes=5), "SHORT")["s54_entry"]


def test_log_integrity_after_forward_run():
    from phase56.forward.audit import audit_log_integrity
    from phase56.config import LOGS

    if not (LOGS / "s54_forward_trades.csv").exists():
        return
    tr = pd.read_csv(LOGS / "s54_forward_trades.csv")
    if len(tr) < 10:
        return
    audit = audit_log_integrity()
    assert audit["pass"], audit.get("issues")

