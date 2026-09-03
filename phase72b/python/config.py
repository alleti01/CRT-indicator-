"""Frozen Phase72A autonomous trader parameters — mirrors Pine inputs."""
from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class PineConfig:
    """Defaults from phase72a_autonomous_trader.pine grpCore + grpP71."""

    warmup: int = 100
    struct_gap: int = 30
    take_threshold: int = 4
    armed_min_score: int = 2
    armed_timeout_bars: int = 15
    swing_period: int = 5
    m1_stop_atr: float = 1.0
    p58_stop_atr: float = 0.75
    target_r: float = 2.5
    max_hold_bars: int = 60
    body_thresh_atr: float = 0.3
    max_chase_atr: float = 1.5
    cooldown_bars: int = 3
    max_wait_bars: int = 2
    decel_lookback: int = 3
    micro_shift_bars: int = 2
    wick_rejection_pct: float = 0.5
    ct_pullback: float = 0.5
    ct_reversal: float = 0.85
    progress_lb_1m: int = 8
    progress_lb_5m: int = 5
    progress_lb_15m: int = 4
    strong_progress_atr: float = 1.0
    weak_progress_atr: float = 0.3
    t5_bars: int = 15
    t5_mfe_r: float = 1.0
    enable_t5: bool = True
    atr_period: int = 14

    def as_dict(self) -> dict:
        return asdict(self)


DEFAULT_CFG = PineConfig()
