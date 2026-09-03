"""Phase58J synthetic adversarial unit tests."""
from __future__ import annotations

import numpy as np
import pytest

from phase58j.research.independent_simulator import init_levels, simulate_bar_path


def _bars(n=20, base=100.0):
    hi = np.full(n, base + 2.0)
    lo = np.full(n, base - 2.0)
    cl = np.full(n, base)
    atr = np.full(n, 4.0)
    return hi, lo, cl, atr


def test_long_stop():
    hi, lo, cl, atr = _bars()
    lo[5] = 90.0
    r = simulate_bar_path(hi, lo, cl, 3, "LONG", 100.0, 1.0, atr, 2.5, 60)
    assert r.exit_reason == "STOP"
    assert abs(r.gross_r + 1.0) < 1e-9


def test_short_stop():
    hi, lo, cl, atr = _bars()
    hi[5] = 110.0
    r = simulate_bar_path(hi, lo, cl, 3, "SHORT", 100.0, 1.0, atr, 2.5, 60)
    assert r.exit_reason == "STOP"
    assert abs(r.gross_r + 1.0) < 1e-9


def test_long_target():
    hi, lo, cl, atr = _bars()
    hi[5] = 120.0
    r = simulate_bar_path(hi, lo, cl, 3, "LONG", 100.0, 1.0, atr, 2.5, 60)
    assert r.exit_reason == "TARGET"
    assert abs(r.gross_r - 2.5) < 1e-9


def test_same_bar_collision_stop_first():
    hi, lo, cl, atr = _bars()
    hi[5] = 120.0
    lo[5] = 90.0
    r = simulate_bar_path(hi, lo, cl, 3, "LONG", 100.0, 1.0, atr, 2.5, 60)
    assert r.collision_bar
    assert r.exit_reason == "STOP"


def test_time_exit():
    hi, lo, cl, atr = _bars(80)
    r = simulate_bar_path(hi, lo, cl, 3, "LONG", 100.0, 1.0, atr, 2.5, 60)
    assert r.exit_reason == "TIME"
    assert r.exit_i == 63


def test_entry_bar_not_eligible():
    hi, lo, cl, atr = _bars()
    lo[3] = 90.0
    hi[3] = 120.0
    r = simulate_bar_path(hi, lo, cl, 3, "LONG", 100.0, 1.0, atr, 2.5, 60)
    assert r.exit_i > 3


def test_m1_wider_stop_m0_survives():
    hi, lo, cl, atr = _bars()
    lo[5] = 97.0
    m0 = simulate_bar_path(hi, lo, cl, 3, "LONG", 100.0, 0.75, atr, 2.5, 60)
    m1 = simulate_bar_path(hi, lo, cl, 3, "LONG", 100.0, 1.0, atr, 2.5, 60)
    assert m0.exit_reason == "STOP"
    assert m1.exit_reason == "TIME"


def test_target_scaling_2p5r():
    stop, target, risk = init_levels("LONG", 100.0, 4.0, 1.0, 2.5)
    assert abs(risk - 4.0) < 1e-9
    assert abs(target - 100.0 - 2.5 * 4.0) < 1e-9


def test_truncation_invariance():
    hi, lo, cl, atr = _bars(80)
    full = simulate_bar_path(hi, lo, cl, 3, "LONG", 100.0, 1.0, atr, 2.5, 60)
    partial = simulate_bar_path(hi[:10], lo[:10], cl[:10], 3, "LONG", 100.0, 1.0, atr[:10], 2.5, 60)
    assert full.stop == partial.stop
    assert full.target == partial.target
