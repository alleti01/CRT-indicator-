"""Causal sideways / structural-escape metrics. Replay and tests only.

known_at for every field is the close of the last completed bar in `bars`.
No future bars, no right-side pivots, no outcome leakage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from phase73.market_data.bar import Bar
from phase74.quality.gates import QualityGateConfig, _recent_bodies_agree

TIGHT_CHOP = "TIGHT_CHOP"
TRENDING = "TRENDING"
SIDEWAYS_WIDE_RANGE = "SIDEWAYS_WIDE_RANGE"
RANGE_ESCAPE = "RANGE_ESCAPE"
RANGE_ESCAPE_CONFIRMED = "RANGE_ESCAPE_CONFIRMED"
FALSE_BREAK = "FALSE_BREAK"


@dataclass(frozen=True)
class SidewaysOverlayConfig:
    """Thresholds chosen from the predeclared replay grid, not per-trade fit."""

    enabled: bool = False
    apply_outside_rth_only: bool = True
    lookback_bars: int = 20
    tight_chop_atr: float = 2.0
    efficiency_max: float = 0.25
    overlap_min: float = 0.45
    close_through_buffer_atr: float = 0.0
    retest_lookback: int = 8

    @classmethod
    def from_dict(cls, raw: dict) -> SidewaysOverlayConfig:
        return cls(
            enabled=bool(raw.get("enabled", False)),
            apply_outside_rth_only=bool(raw.get("apply_outside_rth_only", True)),
            lookback_bars=int(raw.get("lookback_bars", 20)),
            tight_chop_atr=float(raw.get("tight_chop_atr", 2.0)),
            efficiency_max=float(raw.get("efficiency_max", 0.25)),
            overlap_min=float(raw.get("overlap_min", 0.45)),
            close_through_buffer_atr=float(raw.get("close_through_buffer_atr", 0.0)),
            retest_lookback=int(raw.get("retest_lookback", 8)),
        )


@dataclass(frozen=True)
class WindowMetrics:
    range_width_20: float
    range_atr_20: float
    net_progress_20: float
    total_path_20: float
    directional_efficiency_20: float
    adjacent_overlap_ratio: float
    range_upper_prebreak: float
    range_lower_prebreak: float
    close: float
    high: float
    low: float
    continuation_3_of_4: bool


@dataclass(frozen=True)
class EscapeResult:
    close_through: bool
    retest_hold: bool
    retest_fail: bool
    valid: bool
    route: str


def _pair_overlap(a: Bar, b: Bar) -> float:
    inter = min(a.high, b.high) - max(a.low, b.low)
    union = max(a.high, b.high) - min(a.low, b.low)
    if union <= 0:
        return 0.0
    return max(0.0, inter) / union


def compute_window_metrics(
    bars: Sequence[Bar],
    direction: str,
    atr: float,
    cfg: SidewaysOverlayConfig | None = None,
    gate_cfg: QualityGateConfig | None = None,
) -> WindowMetrics | None:
    """20-bar efficiency / overlap / frozen pre-break boundary.

    known_at: close of bars[-1]
    lookback: last `lookback_bars` completed 1m bars, inclusive of decision bar
    range_upper_prebreak / range_lower_prebreak known_at: close of bars[-2]
        (high/low of the decision bar cannot raise the escape wall)
    """
    cfg = cfg or SidewaysOverlayConfig()
    gate_cfg = gate_cfg or QualityGateConfig()
    if atr is None or atr <= 0 or len(bars) < cfg.lookback_bars:
        return None
    window = list(bars)[-cfg.lookback_bars :]
    prior = window[:-1]
    current = window[-1]
    highs = [b.high for b in window]
    lows = [b.low for b in window]
    range_width = max(highs) - min(lows)
    range_atr = range_width / atr
    net_progress = abs(current.close - window[0].close)
    total_path = 0.0
    for i in range(1, len(window)):
        total_path += abs(window[i].close - window[i - 1].close)
    efficiency = (net_progress / total_path) if total_path > 0 else 0.0
    overlaps = [_pair_overlap(window[i - 1], window[i]) for i in range(1, len(window))]
    overlap = sum(overlaps) / len(overlaps) if overlaps else 0.0
    return WindowMetrics(
        range_width_20=range_width,
        range_atr_20=range_atr,
        net_progress_20=net_progress,
        total_path_20=total_path,
        directional_efficiency_20=efficiency,
        adjacent_overlap_ratio=overlap,
        range_upper_prebreak=max(b.high for b in prior),
        range_lower_prebreak=min(b.low for b in prior),
        close=current.close,
        high=current.high,
        low=current.low,
        continuation_3_of_4=_recent_bodies_agree(
            window, direction, gate_cfg.pa_lookback_bars, gate_cfg.pa_min_bodies
        ),
    )


def detect_false_break(metrics: WindowMetrics, direction: str) -> bool:
    """Wick beyond frozen pre-break wall, close back inside.

    known_at: close of the decision bar. Boundary is bars[:-1] only.
    """
    upper = metrics.range_upper_prebreak
    lower = metrics.range_lower_prebreak
    if direction == "LONG":
        return metrics.high > upper and metrics.close <= upper
    return metrics.low < lower and metrics.close >= lower


def detect_close_through(
    metrics: WindowMetrics, direction: str, buffer_atr: float, atr: float
) -> bool:
    """Route A: close materially outside the frozen pre-break boundary."""
    buf = max(0.0, buffer_atr) * atr
    if direction == "LONG":
        return metrics.close > metrics.range_upper_prebreak + buf
    return metrics.close < metrics.range_lower_prebreak - buf


def detect_retest_hold(
    bars: Sequence[Bar],
    direction: str,
    atr: float,
    cfg: SidewaysOverlayConfig | None = None,
) -> tuple[bool, bool]:
    """Route B: prior close-through, pullback to frozen wall, wall holds.

    For candidate bar i, boundary is max/min of bars[:i] only (pre-break).
    Returns (retest_hold, retest_fail).
    """
    cfg = cfg or SidewaysOverlayConfig()
    if atr <= 0 or len(bars) < 4:
        return False, False
    window = list(bars)[-cfg.lookback_bars :]
    buf = max(0.0, cfg.close_through_buffer_atr) * atr
    start = max(1, len(window) - cfg.retest_lookback - 1)
    hold = False
    fail = False
    for i in range(start, len(window) - 1):
        prior = window[:i]
        if len(prior) < 2:
            continue
        upper = max(b.high for b in prior)
        lower = min(b.low for b in prior)
        brk = window[i]
        if direction == "LONG":
            if brk.close <= upper + buf:
                continue
            after = window[i + 1 :]
            touched = any(b.low <= upper for b in after)
            closed_back = any(b.close <= upper for b in after)
            last = after[-1]
            if touched and closed_back:
                fail = True
            elif touched and last.close > upper and all(b.close > upper for b in after):
                hold = True
        else:
            if brk.close >= lower - buf:
                continue
            after = window[i + 1 :]
            touched = any(b.high >= lower for b in after)
            closed_back = any(b.close >= lower for b in after)
            last = after[-1]
            if touched and closed_back:
                fail = True
            elif touched and last.close < lower and all(b.close < lower for b in after):
                hold = True
    return hold, fail


def detect_structural_escape(
    bars: Sequence[Bar],
    direction: str,
    atr: float,
    metrics: WindowMetrics,
    cfg: SidewaysOverlayConfig | None = None,
) -> EscapeResult:
    cfg = cfg or SidewaysOverlayConfig()
    close_through = detect_close_through(
        metrics, direction, cfg.close_through_buffer_atr, atr
    )
    retest_hold, retest_fail = detect_retest_hold(bars, direction, atr, cfg)
    if retest_hold:
        return EscapeResult(close_through, True, False, True, "retest")
    if close_through:
        return EscapeResult(True, False, retest_fail, True, "close_through")
    return EscapeResult(False, False, retest_fail, False, "")


def detect_sideways_state(
    metrics: WindowMetrics,
    cfg: SidewaysOverlayConfig | None = None,
) -> bool:
    """Wide box + low efficiency + high overlap. Not a mixed-candle veto.

    Structural escape is a *release*, not part of this predicate.
    """
    cfg = cfg or SidewaysOverlayConfig()
    if metrics.range_atr_20 < cfg.tight_chop_atr:
        return False
    if metrics.directional_efficiency_20 > cfg.efficiency_max:
        return False
    if metrics.adjacent_overlap_ratio < cfg.overlap_min:
        return False
    return True


def classify_market_state(
    metrics: WindowMetrics,
    escape: EscapeResult,
    false_break: bool,
    cfg: SidewaysOverlayConfig | None = None,
) -> str:
    cfg = cfg or SidewaysOverlayConfig()
    if metrics.range_atr_20 < cfg.tight_chop_atr:
        return TIGHT_CHOP
    sideways = detect_sideways_state(metrics, cfg)
    if sideways and false_break:
        return FALSE_BREAK
    if sideways and escape.route == "retest":
        return RANGE_ESCAPE_CONFIRMED
    if sideways and escape.valid:
        return RANGE_ESCAPE
    if sideways:
        return SIDEWAYS_WIDE_RANGE
    return TRENDING
