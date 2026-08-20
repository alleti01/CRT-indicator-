import pandas as pd

from phase16.config import FrozenConfig
from phase16.models import SetupEvent, StructureEvent
from phase16.retest_reclaim_research import ReclaimGate


TZ = "America/Chicago"


def _ts(minute: int) -> pd.Timestamp:
    return pd.Timestamp("2026-07-01 09:30", tz=TZ) + pd.Timedelta(minutes=5 * minute)


def _setup(direction: int = 0) -> SetupEvent:
    return SetupEvent(
        canonical_long=direction == 1,
        canonical_short=direction == -1,
        canonical_score=85 if direction else 0,
        htf_regime=1,
        session_bucket=2,
    )


def _structure(*, bull=False, bear=False, high=100.0, low=100.0) -> StructureEvent:
    return StructureEvent(
        bull_bos=bull,
        bear_bos=bear,
        previous_active_high=high,
        previous_active_low=low,
        active_high=high,
        active_low=low,
    )


def _step(gate, i, *, o, h, l, c, setup=None, structure=None):
    return gate.step(
        bar_index=i,
        timestamp=_ts(i),
        open_price=o,
        high=h,
        low=l,
        close=c,
        atr=10.0,
        setup=setup or _setup(),
        structure=structure or _structure(),
    )


def test_short_sequence_requires_distinct_retest_reclaim_and_confirm_bars():
    lookup = {(-1, int(_ts(0).value)): 1}
    gate = ReclaimGate(FrozenConfig(), 0.30, 3, lookup)

    assert _step(
        gate,
        0,
        o=101,
        h=101,
        l=98,
        c=99,
        setup=_setup(-1),
        structure=_structure(bear=True, low=100),
    ) is None
    assert gate.state == 2  # Same-bar setup+BOS, but no same-bar retest.

    assert _step(gate, 1, o=100, h=102, l=99, c=101.5) is None
    assert gate.state == 3

    assert _step(gate, 2, o=101, h=101.5, l=99, c=99.5) is None
    assert gate.state == 4  # Reclaim cannot confirm on its own bar.

    entry = _step(gate, 3, o=99.8, h=100, l=98, c=99.0)
    assert entry is not None
    assert entry.candidate_id == 1
    assert entry.retest_timestamp == _ts(1)
    assert entry.reclaim_timestamp == _ts(2)
    assert entry.entry_timestamp == _ts(3)


def test_short_maximum_close_penetration_is_terminal():
    gate = ReclaimGate(
        FrozenConfig(), 0.20, 3, {(-1, int(_ts(0).value)): 2}
    )
    _step(
        gate,
        0,
        o=101,
        h=101,
        l=98,
        c=99,
        setup=_setup(-1),
        structure=_structure(bear=True, low=100),
    )
    _step(gate, 1, o=100, h=103, l=99, c=102.5)
    assert gate.state == 0
    assert gate.outcomes[-1]["gate_result"] == "MAX_PENETRATION_WAIT_RETEST"


def test_long_is_exact_directional_mirror():
    gate = ReclaimGate(
        FrozenConfig(), 0.30, 2, {(1, int(_ts(0).value)): 3}
    )
    _step(
        gate,
        0,
        o=99,
        h=102,
        l=99,
        c=101,
        setup=_setup(1),
        structure=_structure(bull=True, high=100),
    )
    assert gate.state == 2
    _step(gate, 1, o=100, h=101, l=98, c=98.5)
    assert gate.state == 3
    _step(gate, 2, o=99, h=101, l=98.5, c=100.5)
    assert gate.state == 4
    entry = _step(gate, 3, o=100.2, h=102, l=100, c=101)
    assert entry is not None
    assert entry.direction == 1

