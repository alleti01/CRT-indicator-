"""Market-agnostic adapter interfaces for universal options wall module."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Optional

import pandas as pd


@dataclass(frozen=True)
class ContractSpec:
    """Instrument mechanics handled through adapters."""
    symbol: str
    tick_size: float
    multiplier: float
    session_open: str
    session_close: str
    timezone: str


@dataclass(frozen=True)
class OptionsSnapshot:
    """Point-in-time options chain snapshot."""
    timestamp: pd.Timestamp
    underlying: str
    mapping: str
    spot: float
    chain: pd.DataFrame
    known_at: pd.Timestamp
    snapshot_id: str


@dataclass(frozen=True)
class WallSnapshot:
    """Computed wall candidate at a point in time."""
    timestamp: pd.Timestamp
    underlying: str
    mapping: str
    wall_family: str
    wall_id: str
    strike: float
    wall_value: float
    wall_rank: int
    wall_strength_percentile: float
    expiration_bucket: str
    spot: float
    distance_from_spot: float
    distance_atr: float
    source_snapshot_timestamp: pd.Timestamp
    valid_from: pd.Timestamp
    valid_until: Optional[pd.Timestamp]
    method_version: str


class UnderlyingAdapter(ABC):
    """Load and normalize underlying price bars."""

    @abstractmethod
    def contract_spec(self) -> ContractSpec:
        ...

    @abstractmethod
    def load_bars(self, timeframe: str = "1M") -> pd.DataFrame:
        ...

    @abstractmethod
    def atr_at(self, ts: pd.Timestamp, bars: pd.DataFrame) -> float:
        ...


class OptionsAdapter(ABC):
    """Load point-in-time options snapshots."""

    @abstractmethod
    def mapping_id(self) -> str:
        ...

    @abstractmethod
    def underlying_symbol(self) -> str:
        ...

    @abstractmethod
    def options_product(self) -> str:
        ...

    @abstractmethod
    def iter_snapshots(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> Iterator[OptionsSnapshot]:
        ...

    @abstractmethod
    def provenance(self) -> dict:
        ...


class ExpirationCalendar(ABC):
    """Expiration bucket assignment."""

    @abstractmethod
    def dte(self, as_of: pd.Timestamp, expiration: pd.Timestamp) -> int:
        ...

    @abstractmethod
    def bucket(self, dte: int) -> str:
        ...


class WallCalculator(ABC):
    """Compute wall candidates from a causal options snapshot."""

    @abstractmethod
    def family(self) -> str:
        ...

    @abstractmethod
    def compute(
        self,
        snapshot: OptionsSnapshot,
        atr: float,
        expiration_scope: str,
    ) -> list[WallSnapshot]:
        ...


class InteractionDetector(ABC):
    """Detect price interactions with known walls."""

    @abstractmethod
    def update(
        self,
        bar: pd.Series,
        bar_i: int,
        active_walls: list[WallSnapshot],
    ) -> list[dict]:
        ...


class EpisodeEngine(ABC):
    """Consolidate repeated observations into distinct episodes."""

    @abstractmethod
    def consolidate(self, interactions: pd.DataFrame) -> pd.DataFrame:
        ...


class ExecutionModel(ABC):
    """Separate signal time from execution time."""

    @abstractmethod
    def execute(
        self,
        signal: dict,
        bars: pd.DataFrame,
        signal_i: int,
        cost_mult: float = 1.0,
        tick_slippage: int = 0,
    ) -> dict:
        ...
