"""hyp_R simulation matches phase73 M0 management + NQ.cost_r."""
from __future__ import annotations

import numpy as np
import pytest

from phase58.research.instrument import NQ
from signal_ledger.hypothetical_outcomes import apply_m0_cost, hyp_m0_long_r, hyp_m0_short_r, walk_m0_phase73


def _market(n=50, base=100.0):
    hi = np.full(n, base + 0.4)
    lo = np.full(n, base - 0.4)
    cl = np.full(n, base)
    op = np.full(n, base)
    atr = np.full(n, 1.0)
    return hi, lo, cl, op, atr


def _expected_net(gross: float, entry: float, risk: float = 1.0) -> float:
    return apply_m0_cost(gross, entry, risk)


class TestHypM0LongStop:
    def test_long_stop_matches_phase73_net(self):
        hi, lo, cl, op, atr = _market(50)
        signal_i = 10
        ei = 11
        ep = float(op[ei])
        for k in range(ei + 1, 20):
            lo[k] = 98.0
        hyp = hyp_m0_long_r(hi, lo, cl, op, atr, signal_i)
        ref = walk_m0_phase73(hi, lo, cl, op, atr, ei, "LONG", ep, 1.0)
        assert hyp == pytest.approx(ref)
        assert hyp == pytest.approx(_expected_net(-1.0, ep))


class TestHypM0LongTarget:
    def test_long_target_net(self):
        hi, lo, cl, op, atr = _market(50)
        signal_i = 10
        ei = 11
        ep = float(op[ei])
        for k in range(ei + 1, 30):
            hi[k] = 103.0
        hyp = hyp_m0_long_r(hi, lo, cl, op, atr, signal_i)
        ref = walk_m0_phase73(hi, lo, cl, op, atr, ei, "LONG", ep, 1.0)
        assert hyp == pytest.approx(ref)
        assert hyp == pytest.approx(_expected_net(2.5, ep))


class TestHypM0ShortStop:
    def test_short_stop_net(self):
        hi, lo, cl, op, atr = _market(50)
        signal_i = 10
        ei = 11
        ep = float(op[ei])
        for k in range(ei + 1, 20):
            hi[k] = 102.0
        hyp = hyp_m0_short_r(hi, lo, cl, op, atr, signal_i)
        ref = walk_m0_phase73(hi, lo, cl, op, atr, ei, "SHORT", ep, 1.0)
        assert hyp == pytest.approx(ref)
        assert hyp == pytest.approx(_expected_net(-1.0, ep))


class TestHypM0SameBarCollision:
    def test_stop_first_on_collision(self):
        hi, lo, cl, op, atr = _market(50)
        ei = 5
        ep = 100.0
        op[ei] = ep
        k = ei + 1
        hi[k] = 103.0
        lo[k] = 98.0
        net = walk_m0_phase73(hi, lo, cl, op, atr, ei, "LONG", ep, 1.0)
        assert net == pytest.approx(_expected_net(-1.0, ep))


class TestCostUsesNqCostR:
    def test_cost_matches_instrument_spec(self):
        entry = 21000.0
        risk = 10.0
        cost = NQ.cost_r(entry, entry - risk)
        assert cost == pytest.approx(14.50 / (10.0 * 20.0))
