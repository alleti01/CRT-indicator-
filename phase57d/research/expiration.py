"""Expiration calendar for options wall bucketing."""

from __future__ import annotations

import pandas as pd

from phase57d.config import EXPIRATION_AGGREGATES, EXPIRATION_BUCKETS
from phase57d.research.interfaces import ExpirationCalendar


class StandardExpirationCalendar(ExpirationCalendar):
    """Standard DTE bucket assignment."""

    def dte(self, as_of: pd.Timestamp, expiration: pd.Timestamp) -> int:
        as_of = pd.Timestamp(as_of).normalize()
        exp = pd.Timestamp(expiration).normalize()
        return max(0, (exp - as_of).days)

    def bucket(self, dte: int) -> str:
        for name, (lo, hi) in EXPIRATION_BUCKETS.items():
            if lo <= dte <= hi:
                return name
        return "31-60DTE" if dte > 60 else "0DTE"

    def in_aggregate(self, dte: int, aggregate: str) -> bool:
        if aggregate == "0DTE":
            return dte == 0
        if aggregate == "0-5D":
            return 0 <= dte <= 5
        if aggregate == "0-14D":
            return 0 <= dte <= 14
        if aggregate == "<=30D":
            return 0 <= dte <= 30
        raise ValueError(f"Unknown aggregate: {aggregate}")

    @staticmethod
    def valid_aggregates() -> tuple[str, ...]:
        return EXPIRATION_AGGREGATES
