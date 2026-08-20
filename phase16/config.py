"""Frozen settings extracted from CRT_Core_Phase15_ROBUSTNESS_VALIDATION.pine.

PHASE 16 IS VALIDATION ONLY. Do not tune these values in response to results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(frozen=True)
class FrozenConfig:
    """FROZEN — DO NOT OPTIMIZE DURING PHASE 16."""

    exchange_timezone: str = "America/Chicago"
    chart_minutes: int = 5
    minimum_tick: float = 0.25

    # Phase 1: CRT range (empty Pine input means chart timeframe).
    crt_timeframe: str = ""

    # Phase 2: display liquidity pivots/equal levels.
    phase2_pivot_left: int = 5
    phase2_pivot_right: int = 5
    phase2_atr_length: int = 14
    phase2_equal_atr_tolerance: float = 0.10
    phase2_confirm_sweep: bool = False

    # Phase 3: market structure.
    structure_left: int = 5
    structure_right: int = 5
    structure_break_mode: str = "Close"

    # Phase 4: liquidity engine used by the setup engine.
    liquidity_left: int = 5
    liquidity_right: int = 5
    liquidity_equal_ticks: int = 4
    liquidity_max_levels: int = 100

    # Phase 5: setup quality engine.
    se_min_score: int = 70
    se_strong_score: int = 85
    se_liquidity_lookback: int = 20
    se_displacement_lookback: int = 10
    se_displacement_multiplier: float = 1.5
    se_strict_session: bool = False
    se_preferred_session: str = "0930-1600"
    se_anti_chase: bool = True
    se_chase_atr_max: float = 3.0
    se_cooldown_bars: int = 5

    # Frozen Variant-C HTF/session eligibility.
    htf_timeframe_minutes: int = 60
    htf_fast_ema: int = 20
    htf_slow_ema: int = 50
    htf_atr_length: int = 14
    htf_neutral_atr_threshold: float = 0.10

    # Phase 12/14 entry funnel.
    p12_expiry_bars: int = 8
    p12_retest_atr_tolerance: float = 0.10

    # Phase 14 trade simulation.
    trade_stop_atr: float = 1.5
    trade_target_r: float = 2.0
    trade_max_minutes: int = 60

    # Development window requested for Phase 16 parity.
    development_start: str = "2026-06-29"
    development_end: str = "2026-08-18"

    @property
    def trade_max_bars(self) -> int:
        return max(1, round(self.trade_max_minutes / self.chart_minutes))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DEFAULT_CONFIG = FrozenConfig()


def write_frozen_config(path: Path, config: FrozenConfig = DEFAULT_CONFIG) -> None:
    """Write the resolved frozen settings next to a run's results."""
    import json

    path.write_text(json.dumps(config.to_dict(), indent=2, sort_keys=True) + "\n")

