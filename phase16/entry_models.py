"""Phase 14 Control/BOS/Retest/Confirm event funnel."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd

from .config import FrozenConfig
from .models import EntryEvent, SetupEvent, StructureEvent


STATE_NAMES = {0: "IDLE", 1: "WAIT_BOS", 2: "WAIT_RETEST", 3: "WAIT_CONFIRM"}


@dataclass
class EntryFunnel:
    config: FrozenConfig
    state: int = 0
    direction: int = 0
    setup_bar: int = -1
    bos_bar: int = -1
    retest_bar: int = -1
    score: float = 0.0
    bos_level: float = float("nan")
    setup_timestamp: Optional[pd.Timestamp] = None
    bos_timestamp: Optional[pd.Timestamp] = None
    retest_timestamp: Optional[pd.Timestamp] = None

    @property
    def state_name(self) -> str:
        return STATE_NAMES.get(self.state, "IDLE")

    def _entry(
        self,
        model: str,
        timestamp: pd.Timestamp,
        htf_regime: int,
        session_bucket: int,
        *,
        confirm_timestamp: Optional[pd.Timestamp] = None,
    ) -> EntryEvent:
        if self.setup_timestamp is None:
            raise RuntimeError("funnel has no originating setup")
        return EntryEvent(
            model=model,
            direction=self.direction,
            score=self.score,
            entry_timestamp=timestamp,
            setup_timestamp=self.setup_timestamp,
            bos_timestamp=self.bos_timestamp,
            retest_timestamp=self.retest_timestamp,
            confirm_timestamp=confirm_timestamp,
            htf_regime=htf_regime,
            session_bucket=session_bucket,
        )

    def step(
        self,
        *,
        bar_index: int,
        timestamp: pd.Timestamp,
        open_price: float,
        high: float,
        low: float,
        close: float,
        atr: float,
        setup: SetupEvent,
        structure: StructureEvent,
    ) -> List[EntryEvent]:
        entries: List[EntryEvent] = []

        # Control sees every canonical opportunity independently of funnel state.
        if setup.canonical:
            direction = setup.canonical_direction
            entries.append(
                EntryEvent(
                    model="Control",
                    direction=direction,
                    score=setup.canonical_score,
                    entry_timestamp=timestamp,
                    setup_timestamp=timestamp,
                    htf_regime=setup.htf_regime,
                    session_bucket=setup.session_bucket,
                )
            )

        # Parent funnel accepts a canonical setup only while idle.
        if setup.canonical and self.state == 0:
            self.state = 1
            self.direction = setup.canonical_direction
            self.setup_bar = bar_index
            self.bos_bar = -1
            self.retest_bar = -1
            self.bos_level = float("nan")
            self.score = setup.canonical_score
            self.setup_timestamp = timestamp
            self.bos_timestamp = None
            self.retest_timestamp = None

        # Deliberately separate ``if``: Pine can accept a same-bar BOS after a
        # setup starts. Only retest and confirm are constrained to later bars.
        if self.state == 1:
            bos_ok = (
                self.direction == 1 and structure.bull_bos
            ) or (self.direction == -1 and structure.bear_bos)
            opposite_bos = (
                self.direction == 1 and structure.bear_bos
            ) or (self.direction == -1 and structure.bull_bos)
            if bos_ok:
                prior = (
                    structure.previous_active_high
                    if self.direction == 1
                    else structure.previous_active_low
                )
                current = structure.active_high if self.direction == 1 else structure.active_low
                self.bos_level = prior if math.isfinite(prior) else current
                self.bos_bar = bar_index
                self.bos_timestamp = timestamp
                entries.append(
                    self._entry(
                        "BOS", timestamp, setup.htf_regime, setup.session_bucket
                    )
                )
                self.state = 2
            elif opposite_bos or bar_index - self.setup_bar > self.config.p12_expiry_bars:
                self.state = 0

        elif self.state == 2 and math.isfinite(self.bos_level):
            tolerance = (atr if math.isfinite(float(atr)) else 1.0) * self.config.p12_retest_atr_tolerance
            eligible = self.bos_bar >= 0 and bar_index > self.bos_bar
            touched = eligible and (
                low <= self.bos_level + tolerance
                if self.direction == 1
                else high >= self.bos_level - tolerance
            )
            invalid = eligible and (
                close < self.bos_level - tolerance
                if self.direction == 1
                else close > self.bos_level + tolerance
            )
            # Exact order: invalidation is evaluated before retest touch.
            if invalid:
                self.state = 0
            elif touched:
                self.retest_bar = bar_index
                self.retest_timestamp = timestamp
                entries.append(
                    self._entry(
                        "Retest", timestamp, setup.htf_regime, setup.session_bucket
                    )
                )
                self.state = 3
            elif self.bos_bar >= 0 and bar_index - self.bos_bar > self.config.p12_expiry_bars:
                self.state = 0

        elif self.state == 3 and math.isfinite(self.bos_level) and self.retest_bar >= 0:
            tolerance = (atr if math.isfinite(float(atr)) else 1.0) * self.config.p12_retest_atr_tolerance
            eligible = bar_index > self.retest_bar
            confirmed = eligible and (
                (close > open_price and close > self.bos_level)
                if self.direction == 1
                else (close < open_price and close < self.bos_level)
            )
            invalid = eligible and (
                close < self.bos_level - tolerance
                if self.direction == 1
                else close > self.bos_level + tolerance
            )
            # Exact order: confirmation wins over confirmation invalidation.
            if confirmed:
                entries.append(
                    self._entry(
                        "Confirm",
                        timestamp,
                        setup.htf_regime,
                        setup.session_bucket,
                        confirm_timestamp=timestamp,
                    )
                )
                self.state = 0
            elif invalid or bar_index - self.retest_bar > self.config.p12_expiry_bars:
                self.state = 0
        return entries

