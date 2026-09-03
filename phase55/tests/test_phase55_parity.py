"""Phase55 parity test suite."""

from __future__ import annotations

import pandas as pd

from phase55.implementation.s54_episodes import S54EpisodeState, consolidate_batch, episode_event_order
from phase55.implementation.s54_events import S54EventDetector, batch_events


def test_event_detector_matches_batch():
    from phase53.research.data import load_markets

    m1, _, _ = load_markets()
    m1 = m1.iloc[:8000]
    a = batch_events(m1)
    b = S54EventDetector(m1).run_all()
    assert len(a) == len(b)
    m = a.merge(b, on=["timestamp_ct", "event_type", "direction"])
    assert len(m) == len(a)


def test_30m_boundary_inclusive():
    st = S54EpisodeState(window_min=30)
    t0 = pd.Timestamp("2021-01-04 10:00:00", tz="America/Chicago")
    st.process(t0, "LONG")
    r29 = st.process(t0 + pd.Timedelta(minutes=29), "LONG")
    st2 = S54EpisodeState(window_min=30)
    st2.process(t0, "LONG")
    r30 = st2.process(t0 + pd.Timedelta(minutes=30), "LONG")
    st3 = S54EpisodeState(window_min=30)
    st3.process(t0, "LONG")
    r31 = st3.process(t0 + pd.Timedelta(minutes=31), "LONG")
    assert r29["suppressed"] is True
    assert r30["suppressed"] is True
    assert r31["s54_entry"] is True


def test_opposite_direction_not_blocked():
    st = S54EpisodeState(window_min=30)
    t0 = pd.Timestamp("2021-01-04 10:00:00", tz="America/Chicago")
    st.process(t0, "LONG")
    r = st.process(t0 + pd.Timedelta(minutes=8), "SHORT")
    assert r["s54_entry"] is True


def test_episode_state_matches_consolidate():
    rows = [
        {"timestamp_ct": pd.Timestamp("2021-01-04 10:00:00", tz="America/Chicago"), "direction": "LONG", "event_id": "A", "score": 0.9},
        {"timestamp_ct": pd.Timestamp("2021-01-04 10:10:00", tz="America/Chicago"), "direction": "LONG", "event_id": "B", "score": 0.95},
        {"timestamp_ct": pd.Timestamp("2021-01-04 10:20:00", tz="America/Chicago"), "direction": "SHORT", "event_id": "C", "score": 0.92},
    ]
    df = pd.DataFrame(rows)
    ret, sup = consolidate_batch(df, 30)
    st = S54EpisodeState(window_min=30)
    kept = []
    for _, r in df.iterrows():
        act = st.process(r["timestamp_ct"], r["direction"])
        if act["s54_entry"]:
            kept.append(r["event_id"])
    assert kept == list(ret["event_id"])


def test_same_timestamp_global_order_matters():
    rows = [
        {"timestamp_ct": pd.Timestamp("2021-01-04 10:00:00", tz="America/Chicago"), "direction": "LONG", "event_id": "B", "score": 0.9},
        {"timestamp_ct": pd.Timestamp("2021-01-04 10:00:00", tz="America/Chicago"), "direction": "LONG", "event_id": "A", "score": 0.95},
        {"timestamp_ct": pd.Timestamp("2021-01-04 10:05:00", tz="America/Chicago"), "direction": "LONG", "event_id": "C", "score": 0.92},
    ]
    df = pd.DataFrame(rows)
    global_order = list(episode_event_order(df)["event_id"])
    local_order = list(episode_event_order(df.iloc[[1, 0, 2]])["event_id"])
    assert global_order == ["B", "A", "C"]
    assert local_order == ["A", "B", "C"]
    ret, _ = consolidate_batch(df, 30)
    assert list(ret["event_id"]) == ["B"]


def test_htf_m5_mom_boundaries():
    from phase53.research.data import align_htf_to_1m, load_markets, htf_bar_index
    from phase53.research.features import attach_features
    from phase53.research.core_context import build_core_context, build_p44_state

    m1, m5, m15 = load_markets()
    m5a = align_htf_to_1m(m1, m5)
    m15a = align_htf_to_1m(m1, m15)
    p44 = build_p44_state(m1, m15)
    core = build_core_context(m1)
    # pick bars around 5m boundaries on a liquid day
    day = pd.Timestamp("2024-01-03", tz=m1.index.tz)
    idx = m1.index[(m1.index >= day) & (m1.index < day + pd.Timedelta(days=1))]
    for ts in [pd.Timestamp("2024-01-03 09:04:00", tz=m1.index.tz), pd.Timestamp("2024-01-03 09:05:00", tz=m1.index.tz), pd.Timestamp("2024-01-03 09:09:00", tz=m1.index.tz), pd.Timestamp("2024-01-03 09:10:00", tz=m1.index.tz)]:
        if ts not in m1.index:
            continue
        ii = m1.index.get_loc(ts)
        ev = pd.DataFrame([{"entry_i": ii, "timestamp_ct": ts, "direction": "LONG", "event_type": "E1", "structure_level": 1.0}])
        f = attach_features(ev, m1, m5a, m15a, p44, core)
        j5 = int(htf_bar_index(m1.index, m5a.index)[ii])
        assert pd.notna(f["m5_mom"].iloc[0])
        assert m5a.index[j5] <= ts

