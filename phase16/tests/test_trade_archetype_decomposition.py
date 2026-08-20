import math

import pandas as pd

from phase16.trade_archetype_decomposition import (
    _bh_adjust,
    _retest_behavior,
    sample_label,
    welch_two_sided,
)


def test_retest_behavior_uses_objective_bos_boundary_only():
    assert _retest_behavior(direction=1, probe=100.25, close=100.5, bos_level=100) == "Tolerance-only shallow touch"
    assert _retest_behavior(direction=1, probe=100, close=100.5, bos_level=100) == "Exact BOS touch"
    assert _retest_behavior(direction=1, probe=99.75, close=100.25, bos_level=100) == "Penetration + same-bar reclaim"
    assert _retest_behavior(direction=1, probe=99.75, close=99.75, bos_level=100) == "Penetration without same-bar reclaim"
    assert _retest_behavior(direction=-1, probe=99.75, close=99.5, bos_level=100) == "Tolerance-only shallow touch"
    assert _retest_behavior(direction=-1, probe=100.25, close=99.75, bos_level=100) == "Penetration + same-bar reclaim"


def test_sample_label_locks_minimum_family_size():
    assert sample_label(29) == "SMALL SAMPLE"
    assert sample_label(30) == "ADEQUATE N"


def test_welch_two_sided_is_symmetric():
    a = pd.Series([2.0, 2.1, 1.9, 2.2, 2.0])
    b = pd.Series([-1.0, -0.9, -1.1, -0.8, -1.0])
    t_ab, df_ab, p_ab = welch_two_sided(a, b)
    t_ba, df_ba, p_ba = welch_two_sided(b, a)
    assert t_ab > 0 and t_ba < 0
    assert math.isclose(df_ab, df_ba, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(p_ab, p_ba, rel_tol=0, abs_tol=1e-12)
    assert p_ab < 0.001


def test_bh_adjustment_is_monotone_in_sorted_p_values():
    adjusted = _bh_adjust(pd.Series([0.001, 0.02, 0.2, math.nan]))
    assert adjusted.iloc[0] <= adjusted.iloc[1] <= adjusted.iloc[2]
    assert math.isnan(adjusted.iloc[3])
