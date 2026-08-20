"""Shared value objects used by the backtest components."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional

import pandas as pd


MODELS = ("Control", "BOS", "Retest", "Confirm")


@dataclass
class StructureEvent:
    bull_bos: bool = False
    bear_bos: bool = False
    bull_choch: bool = False
    bear_choch: bool = False
    previous_active_high: float = float("nan")
    previous_active_low: float = float("nan")
    active_high: float = float("nan")
    active_low: float = float("nan")
    bias_before: int = 0
    bias_after: int = 0


@dataclass
class LiquidityEvent:
    bsl_sweep: bool = False
    ssl_sweep: bool = False
    bsl_consumed: bool = False
    ssl_consumed: bool = False

    @property
    def any_sweep(self) -> bool:
        return self.bsl_sweep or self.ssl_sweep


@dataclass
class SetupEvent:
    long_setup: bool = False
    short_setup: bool = False
    long_score: float = 0.0
    short_score: float = 0.0
    canonical_long: bool = False
    canonical_short: bool = False
    canonical_score: float = 0.0
    htf_regime: int = 0
    session_bucket: int = 6

    @property
    def canonical(self) -> bool:
        return self.canonical_long or self.canonical_short

    @property
    def canonical_direction(self) -> int:
        return 1 if self.canonical_long else (-1 if self.canonical_short else 0)


@dataclass
class EntryEvent:
    model: str
    direction: int
    score: float
    entry_timestamp: pd.Timestamp
    setup_timestamp: pd.Timestamp
    bos_timestamp: Optional[pd.Timestamp] = None
    retest_timestamp: Optional[pd.Timestamp] = None
    confirm_timestamp: Optional[pd.Timestamp] = None
    htf_regime: int = 0
    session_bucket: int = 6


@dataclass
class Trade:
    model: str
    direction: int
    setup_timestamp: pd.Timestamp
    bos_timestamp: Optional[pd.Timestamp]
    retest_timestamp: Optional[pd.Timestamp]
    confirm_timestamp: Optional[pd.Timestamp]
    entry_timestamp: pd.Timestamp
    entry_bar: int
    entry_price: float
    stop_price: float
    target_price: float
    risk: float
    score: float
    htf_regime: int
    session_bucket: int
    exit_timestamp: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    result_R: Optional[float] = None
    exit_reason: Optional[str] = None

    def export_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result.pop("entry_bar", None)
        result.pop("risk", None)
        result["direction"] = "Long" if self.direction == 1 else "Short"
        return result

