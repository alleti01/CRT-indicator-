"""Feature attachment — mirrors Phase53 run.py (aligned HTF inputs)."""

from __future__ import annotations

import pandas as pd

from phase53.research.core_context import build_core_context, build_p44_state
from phase53.research.data import align_htf_to_1m
from phase53.research.features import attach_features, feature_columns


def build_feature_context(m1: pd.DataFrame, m5: pd.DataFrame, m15: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Match phase53/run.py: align HTF to 1M before attach_features."""
    p44 = build_p44_state(m1, m15)
    core = build_core_context(m1)
    m5a = align_htf_to_1m(m1, m5)
    m15a = align_htf_to_1m(m1, m15)
    return p44, core, m5a, m15a


def attach_event_features(
    events: pd.DataFrame,
    m1: pd.DataFrame,
    m5: pd.DataFrame,
    m15: pd.DataFrame,
    p44_state: pd.Series | None = None,
    core_ctx: pd.DataFrame | None = None,
    *,
    m5a: pd.DataFrame | None = None,
    m15a: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if events.empty:
        return events
    if m5a is None or m15a is None:
        if p44_state is None or core_ctx is None:
            p44_state, core_ctx, m5a, m15a = build_feature_context(m1, m5, m15)
        else:
            m5a = align_htf_to_1m(m1, m5)
            m15a = align_htf_to_1m(m1, m15)
    elif p44_state is None or core_ctx is None:
        p44_state = build_p44_state(m1, m15)
        core_ctx = build_core_context(m1)
    return attach_features(events, m1, m5a, m15a, p44_state, core_ctx)


def frozen_feature_names(df: pd.DataFrame) -> list[str]:
    return feature_columns(df)
