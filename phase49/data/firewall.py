"""Hard historical / forward separation for Phase 49."""

from __future__ import annotations

import pandas as pd

from phase49.config import DEVELOPMENT_CUTOFF, FORWARD_START_TIMESTAMP, TIMEZONE


class FirewallError(ValueError):
    pass


def development_cutoff_ts() -> pd.Timestamp:
    return pd.Timestamp(DEVELOPMENT_CUTOFF, tz=TIMEZONE)


def forward_start_ts() -> pd.Timestamp:
    return pd.Timestamp(FORWARD_START_TIMESTAMP, tz=TIMEZONE)


def is_development(ts: pd.Timestamp) -> bool:
    t = pd.Timestamp(ts).tz_convert(TIMEZONE)
    return t <= development_cutoff_ts()


def is_forward(ts: pd.Timestamp) -> bool:
    t = pd.Timestamp(ts).tz_convert(TIMEZONE)
    return t >= forward_start_ts()


def split_development_forward(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return df.copy(), df.copy()
    idx = df.index
    dev = df.loc[idx <= development_cutoff_ts()]
    fwd = df.loc[idx >= forward_start_ts()]
    return dev, fwd


def assert_no_overlap(dev: pd.DataFrame, fwd: pd.DataFrame) -> None:
    if dev.empty or fwd.empty:
        return
    overlap = dev.index.intersection(fwd.index)
    if len(overlap):
        raise FirewallError(
            f"development/forward overlap on {len(overlap)} timestamps; first={overlap[0]}"
        )


def assert_development_only(df: pd.DataFrame) -> None:
    if df.empty:
        return
    fwd = df.loc[df.index >= forward_start_ts()]
    if not fwd.empty:
        raise FirewallError(
            f"development loader contains {len(fwd)} forward rows; first={fwd.index[0]}"
        )


def assert_forward_only(df: pd.DataFrame) -> None:
    if df.empty:
        return
    dev = df.loc[df.index < forward_start_ts()]
    if not dev.empty:
        raise FirewallError(
            f"forward loader contains {len(dev)} pre-forward rows; first={dev.index[0]}"
        )


def assert_research_safe(df: pd.DataFrame) -> None:
    """Research loaders (Phase45–48) must not see forward rows."""
    assert_development_only(df)
