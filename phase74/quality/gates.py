"""Pre-fill quality gates: chop, false-break, late-move."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from phase73.market_data.bar import Bar


@dataclass(frozen=True)
class QualityGateConfig:
    lookback_bars: int = 20
    chop_box_atr: float = 2.0
    false_break_percentile: float = 0.15
    false_break_edge_atr: float = 0.25
    late_move_atr: float = 1.0
    max_atr_points: float = 15.0

    @classmethod
    def from_dict(cls, raw: dict) -> QualityGateConfig:
        return cls(
            lookback_bars=int(raw.get("lookback_bars", 20)),
            chop_box_atr=float(raw.get("chop_box_atr", 2.0)),
            false_break_percentile=float(raw.get("false_break_percentile", 0.15)),
            false_break_edge_atr=float(raw.get("false_break_edge_atr", 0.25)),
            late_move_atr=float(raw.get("late_move_atr", 1.0)),
            max_atr_points=float(raw.get("max_atr_points", 15.0)),
        )


@dataclass
class QualityDecision:
    decision: str
    reason: str
    atr: float = 0.0
    box: float = 0.0
    box_atr: float = 0.0
    progress_atr: float = 0.0
    range_low: float = 0.0
    range_high: float = 0.0
    close: float = 0.0
    percentile_in_box: float = 0.0


def evaluate_quality_gates(
    bars: Sequence[Bar],
    direction: str,
    atr: float,
    cfg: QualityGateConfig | None = None,
) -> QualityDecision:
    cfg = cfg or QualityGateConfig()
    if len(bars) < cfg.lookback_bars or atr is None or atr <= 0:
        return QualityDecision(decision="SKIP", reason="SKIP_DATA", atr=float(atr or 0.0))

    window = list(bars)[-cfg.lookback_bars :]
    range_high = max(b.high for b in window)
    range_low = min(b.low for b in window)
    box = range_high - range_low
    close = window[-1].close
    first_close = window[0].close
    last_close = window[-1].close
    if direction == "SHORT":
        progress = first_close - last_close
    else:
        progress = last_close - first_close
    progress_atr = progress / atr
    box_atr = box / atr
    percentile = 0.0 if box <= 0 else (close - range_low) / box

    base = QualityDecision(
        decision="TAKE",
        reason="TAKE",
        atr=atr,
        box=box,
        box_atr=box_atr,
        progress_atr=progress_atr,
        range_low=range_low,
        range_high=range_high,
        close=close,
        percentile_in_box=percentile,
    )

    if box <= 0 or box < cfg.chop_box_atr * atr:
        return QualityDecision(**{**base.__dict__, "decision": "SKIP", "reason": "SKIP_CHOP"})

    edge = cfg.false_break_edge_atr * atr
    if direction == "SHORT":
        at_low = percentile <= cfg.false_break_percentile or close <= range_low + edge
        if at_low:
            return QualityDecision(**{**base.__dict__, "decision": "SKIP", "reason": "SKIP_FALSE_BREAK"})
    else:
        from_high = 0.0 if box <= 0 else (range_high - close) / box
        at_high = from_high <= cfg.false_break_percentile or close >= range_high - edge
        if at_high:
            return QualityDecision(**{**base.__dict__, "decision": "SKIP", "reason": "SKIP_FALSE_BREAK"})

    if progress > cfg.late_move_atr * atr:
        return QualityDecision(**{**base.__dict__, "decision": "SKIP", "reason": "SKIP_LATE_MOVE"})

    if atr > cfg.max_atr_points:
        return QualityDecision(**{**base.__dict__, "decision": "SKIP", "reason": "SKIP_ATR_CAP"})

    return base
