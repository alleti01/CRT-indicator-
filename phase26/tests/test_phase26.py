"""Tests for Phase 26."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from phase26.analyze import gross_r_from_label, net_r
from phase26.labels import _eval_path


def test_eval_path_long_hit():
    close = np.array([100, 101, 102, 103, 104], dtype=float)
    high = close + 1
    low = close - 0.1
    hit, mfe, mae, *_ = _eval_path(0, 3, 1, close, high, low, 2.0, 1.0, 0.5)
    assert hit is True


def test_eval_path_long_stop_first():
    close = np.array([100, 99, 98, 97, 96], dtype=float)
    high = close + 0.2
    low = close - 2
    hit, *_ = _eval_path(0, 3, 1, close, high, low, 2.0, 1.0, 0.5)
    assert hit is False


def test_cost_reduces_r():
    gross = gross_r_from_label(True, 1.0)
    assert gross == 2.0
    net = net_r(gross, atr=20.0)
    assert net < gross
