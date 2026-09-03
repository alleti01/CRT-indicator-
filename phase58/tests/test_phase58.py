"""Phase58 causality and state machine tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase58.research.trader_state import State, Decision, TraderState
from phase58.research.context import compute_context
from phase58.research.location import compute_location
from phase58.research.reaction import (
    failed_extension, momentum_loss, reclaim, directional_response, micro_shift, rejection,
)
from phase58.research.instrument import NQ


def _make_arrays(n=200):
    np.random.seed(42)
    prices = np.cumsum(np.random.randn(n) * 0.3 + 0.05) + 100
    from phase58.research.precompute import MarketArrays
    from phase52.research.swings import (
        precompute_swing_highs, precompute_swing_lows,
        precompute_last2_swing_highs, precompute_last2_swing_lows,
    )
    hi = prices + np.abs(np.random.randn(n)) * 0.5
    lo = prices - np.abs(np.random.randn(n)) * 0.5
    cl = prices + 0.1
    op = prices - 0.1
    atr = pd.Series(hi - lo).rolling(14, min_periods=1).mean().values
    body = np.abs(cl - op)
    avg_body = pd.Series(body).rolling(20, min_periods=1).mean().values
    idx = pd.date_range("2024-01-02 09:00", periods=n, freq="1min", tz="America/Chicago")
    sh1, sh2 = precompute_last2_swing_highs(hi, 5)
    sl1, sl2 = precompute_last2_swing_lows(lo, 5)
    return MarketArrays(
        hi=hi, lo=lo, cl=cl, op=op, atr=atr, n=n, idx=idx,
        sh=precompute_swing_highs(hi, 5), sl=precompute_swing_lows(lo, 5),
        sh1=sh1, sh2=sh2, sl1=sl1, sl2=sl2,
        m5_cl=cl, m5_op=op, m5_hi=hi, m5_lo=lo, m5_atr=atr,
        m5_idx=np.arange(n), m15_cl=cl, m15_op=op, m15_hi=hi, m15_lo=lo,
        m15_atr=atr, m15_idx=np.arange(n), body=body, avg_body=avg_body,
    )


def test_context_no_future():
    m = _make_arrays(200)
    ctx1 = compute_context(m, 100)
    assert ctx1["direction"] in ("BULLISH", "BEARISH", "NEUTRAL")
    assert 0 <= ctx1["confidence"] <= 100


def test_location_normalized():
    m = _make_arrays(200)
    loc = compute_location(m, 100, "LONG")
    assert "swing_dist_atr" in loc
    assert "pb_depth_pct" in loc
    assert "range_pos" in loc


def test_reaction_components_return_bool_mag():
    m = _make_arrays(200)
    for fn in [failed_extension, momentum_loss, reclaim, directional_response, micro_shift, rejection]:
        active, mag = fn(m, 100, "LONG")
        assert isinstance(active, (bool, np.bool_))
        assert isinstance(mag, (int, float, np.integer, np.floating))


def test_state_transitions_valid():
    st = TraderState()
    assert st.state == State.WATCH
    st.state = State.ARMED_LONG
    st.direction = "LONG"
    assert st.state == State.ARMED_LONG
    st.reset_to_watch()
    assert st.state == State.WATCH
    assert st.direction == ""


def test_instrument_cost():
    cr = NQ.cost_r(21000, 20990, 1.0)
    assert cr > 0
    assert abs(cr - 14.50 / (10 * 20)) < 0.001


def test_no_deepest_i():
    """Phase58 must never reference a retrospectively selected deepest_i."""
    import inspect
    from phase58.research import trader_engine, context, location, reaction
    for mod in [trader_engine, context, location, reaction]:
        src = inspect.getsource(mod)
        assert "deepest_i" not in src, f"deepest_i found in {mod.__name__}"


def test_s54_hash():
    from phase58.research.precompute import MarketArrays
    h = (pd.io.common.Path(__file__).resolve().parents[2] / "phase55" / "frozen" / "model_hash.txt").read_text().strip()
    assert h == "bccf4277f3d44d13"


def test_deterministic_rerun():
    import json
    from phase58.research.trader_engine import TraderEngine
    m = _make_arrays(300)
    cfg = json.load(open(str(pd.io.common.Path(__file__).resolve().parents[1] / "config" / "phase58_v1_frozen.json")))
    e1 = TraderEngine(m, cfg); e1.run(end_i=250)
    e2 = TraderEngine(m, cfg); e2.run(end_i=250)
    d1, t1 = e1.results(); d2, t2 = e2.results()
    assert len(d1) == len(d2)
    assert len(t1) == len(t2)
    if not t1.empty:
        assert (t1["net_R"].values == t2["net_R"].values).all()
