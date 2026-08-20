import pandas as pd

from phase16.winner_loser_forensics import (
    NUMERIC_FEATURES,
    OUTCOME_COLUMNS,
    _effect_size,
    _stability_label,
    interaction_analysis,
)


def test_feature_registry_excludes_outcome_labels():
    assert not (set(NUMERIC_FEATURES) & OUTCOME_COLUMNS)


def test_effect_size_has_expected_direction():
    effect = _effect_size(pd.Series([2.0, 3.0, 4.0]), pd.Series([0.0, 1.0, 2.0]))
    assert effect > 0


def test_stability_labels_require_sign_and_magnitude_retention():
    assert _stability_label(1.0, [0.80, 0.90, 1.10])[0] == "STABLE"
    assert _stability_label(1.0, [0.60, 0.80, 1.10])[0] == "PARTIALLY STABLE"
    assert _stability_label(1.0, [-0.20, 0.90, 1.10])[0] == "UNSTABLE"


def test_interaction_search_is_limited_to_ten_preregistered_pairs():
    columns = {feature: [float(index + 1) for index in range(8)] for feature in NUMERIC_FEATURES}
    frame = pd.DataFrame(columns)
    frame["net_R"] = [-1.0, 2.0, -1.0, 2.0, -1.0, 2.0, -1.0, 2.0]
    frame["is_winner"] = (frame.net_R > 0).astype(int)
    frame["session"] = ["Overnight", "Premarket", "Opening", "Morning", "Midday", "Afternoon", "Opening", "Morning"]
    frame["same_bar_setup_bos"] = [True, False] * 4
    interactions = interaction_analysis(frame)
    assert interactions.interaction_id.nunique() == 10
    assert set(interactions.cell) == {"Both", "A only", "B only", "Neither"}

