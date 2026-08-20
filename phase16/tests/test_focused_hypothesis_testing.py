import math

import pandas as pd

from phase16.focused_hypothesis_testing import (
    H1_DISPLACEMENT_MINIMUMS,
    H1_RELATIVE_VOLUME_MINIMUMS,
    H2_RECLAIM_MINIMUMS,
    H2_RETEST_RANGE_MINIMUMS,
    SESSION_NAMES,
    VOLATILITY_STATES,
    _student_t_cdf,
    sample_classification,
    welch_greater,
)


def test_predefined_cell_counts_are_locked():
    assert len(H1_DISPLACEMENT_MINIMUMS) * len(H1_RELATIVE_VOLUME_MINIMUMS) == 36
    assert len(H2_RETEST_RANGE_MINIMUMS) * len(H2_RECLAIM_MINIMUMS) == 36
    assert len(SESSION_NAMES) * len(VOLATILITY_STATES) == 21


def test_sample_classifications_match_preregistered_boundaries():
    assert sample_classification(29) == "INSUFFICIENT"
    assert sample_classification(30) == "VERY WEAK"
    assert sample_classification(50) == "EXPLORATORY"
    assert sample_classification(100) == "BETTER SUPPORTED"


def test_student_t_cdf_is_symmetric_and_centered():
    assert math.isclose(_student_t_cdf(0.0, 10), 0.5, abs_tol=1e-12)
    assert math.isclose(_student_t_cdf(2.0, 10) + _student_t_cdf(-2.0, 10), 1.0, abs_tol=1e-12)


def test_welch_greater_detects_large_positive_shift():
    statistic, degrees, p_value = welch_greater(
        pd.Series([2.0, 2.1, 1.9, 2.2, 2.0]),
        pd.Series([-1.0, -0.9, -1.1, -0.8, -1.0]),
    )
    assert statistic > 0
    assert degrees > 1
    assert p_value < 0.001

