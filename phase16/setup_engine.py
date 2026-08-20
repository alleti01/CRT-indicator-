"""Frozen Phase 5 scoring and Phase 10 Variant-C canonical feed."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from .config import FrozenConfig
from .indicators import is_in_session, session_bucket
from .models import LiquidityEvent, SetupEvent, StructureEvent


@dataclass
class SetupEngine:
    config: FrozenConfig
    bull_structure_bar: int = -1
    bear_structure_bar: int = -1
    bull_is_choch: bool = False
    bear_is_choch: bool = False
    ssl_sweep_bar: int = -1
    bsl_sweep_bar: int = -1
    long_cool_until: int = 0
    short_cool_until: int = 0

    def step(
        self,
        *,
        bar_index: int,
        timestamp: pd.Timestamp,
        open_price: float,
        close: float,
        atr: float,
        body_average: float,
        htf_regime: int,
        structure: StructureEvent,
        liquidity: LiquidityEvent,
    ) -> SetupEvent:
        # Phase 5 consumes same-bar Phase 3/4 events after those phases update.
        if structure.bull_bos:
            self.bull_structure_bar = bar_index
            self.bull_is_choch = structure.bias_before == -1
        if structure.bear_bos:
            self.bear_structure_bar = bar_index
            self.bear_is_choch = structure.bias_before == 1
        if liquidity.ssl_sweep:
            self.ssl_sweep_bar = bar_index
        if liquidity.bsl_sweep:
            self.bsl_sweep_bar = bar_index

        recent_ssl = (
            self.ssl_sweep_bar >= 0
            and bar_index - self.ssl_sweep_bar <= self.config.se_liquidity_lookback
        )
        recent_bsl = (
            self.bsl_sweep_bar >= 0
            and bar_index - self.bsl_sweep_bar <= self.config.se_liquidity_lookback
        )
        recent_bull = (
            self.bull_structure_bar >= 0
            and bar_index - self.bull_structure_bar <= self.config.se_liquidity_lookback
        )
        recent_bear = (
            self.bear_structure_bar >= 0
            and bar_index - self.bear_structure_bar <= self.config.se_liquidity_lookback
        )

        bias = structure.bias_after
        long_liquidity = 25.0 if recent_ssl else 0.0
        short_liquidity = 25.0 if recent_bsl else 0.0
        long_structure = (
            (30.0 if self.bull_is_choch else (30.0 if bias == 1 else 20.0))
            if recent_bull
            else 0.0
        )
        short_structure = (
            (30.0 if self.bear_is_choch else (30.0 if bias == -1 else 20.0))
            if recent_bear
            else 0.0
        )
        long_bias = 20.0 if bias == 1 else (10.0 if bias == 0 else 5.0)
        short_bias = 20.0 if bias == -1 else (10.0 if bias == 0 else 5.0)
        bullish_displacement = (
            close > open_price
            and math.isfinite(float(body_average))
            and body_average > 0
            and (close - open_price) > self.config.se_displacement_multiplier * body_average
        )
        bearish_displacement = (
            close < open_price
            and math.isfinite(float(body_average))
            and body_average > 0
            and (open_price - close) > self.config.se_displacement_multiplier * body_average
        )
        in_preferred_session = is_in_session(timestamp, self.config.se_preferred_session)
        long_score = min(
            long_liquidity
            + long_structure
            + long_bias
            + (15.0 if bullish_displacement else 0.0)
            + (10.0 if in_preferred_session else 0.0),
            100.0,
        )
        short_score = min(
            short_liquidity
            + short_structure
            + short_bias
            + (15.0 if bearish_displacement else 0.0)
            + (10.0 if in_preferred_session else 0.0),
            100.0,
        )

        if self.config.se_anti_chase and math.isfinite(float(atr)) and atr > 0:
            if (
                math.isfinite(structure.active_high)
                and close > structure.active_high
                and close - structure.active_high > self.config.se_chase_atr_max * atr
            ):
                long_score = 0.0
            if (
                math.isfinite(structure.active_low)
                and close < structure.active_low
                and structure.active_low - close > self.config.se_chase_atr_max * atr
            ):
                short_score = 0.0
        if self.config.se_strict_session and not in_preferred_session:
            long_score = 0.0
            short_score = 0.0

        new_long = structure.bull_bos or liquidity.ssl_sweep
        new_short = structure.bear_bos or liquidity.bsl_sweep
        long_setup = (
            bar_index >= self.long_cool_until
            and new_long
            and long_score >= self.config.se_min_score
        )
        short_setup = (
            bar_index >= self.short_cool_until
            and new_short
            and short_score >= self.config.se_min_score
        )
        if long_setup:
            self.long_cool_until = bar_index + self.config.se_cooldown_bars
        if short_setup:
            self.short_cool_until = bar_index + self.config.se_cooldown_bars

        bucket = session_bucket(timestamp)
        live_filter = htf_regime != 0 and bucket != 6
        variant_c = (long_setup or short_setup) and live_filter
        canonical_long = variant_c and long_setup
        # Exact Pine precedence when both directional setup booleans are true.
        canonical_short = variant_c and not long_setup and short_setup
        canonical_score = int(long_score if canonical_long else short_score if canonical_short else 0)
        return SetupEvent(
            long_setup=long_setup,
            short_setup=short_setup,
            long_score=int(long_score),
            short_score=int(short_score),
            canonical_long=canonical_long,
            canonical_short=canonical_short,
            canonical_score=canonical_score,
            htf_regime=int(htf_regime),
            session_bucket=bucket,
        )

