"""Sideways overlay on top of existing gates. Not wired into LiveStack.

Evaluation order (when overlay applies — Globex only by default):

1. session classification
2. existing SKIP_DATA
3. causal 20-bar metrics
4. existing SKIP_CHOP (tight box)
5. existing SKIP_ATR_CAP (hard safety)
6. detect SIDEWAYS_WIDE_RANGE
7. detect structural escape
8. detect false break
9. if sideways + false break → PASS_FALSE_BREAK
   if sideways + no valid escape → PASS_SIDEWAYS_WIDE_RANGE
10. only then existing continuation / TAKE / SKIP_NO_TREND / SKIP_FALSE_BREAK /
    SKIP_LATE_MOVE (`evaluate_quality_gates`)

3-of-4 cannot jump to TAKE before steps 6–9.
RTH (or overlay disabled) returns the existing decision unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from phase73.market_data.bar import Bar
from phase74.quality.day_halt import session_key_ny
from phase74.quality.gates import QualityDecision, QualityGateConfig, evaluate_quality_gates
from phase74.quality.sideways import (
    EscapeResult,
    SidewaysOverlayConfig,
    WindowMetrics,
    classify_market_state,
    compute_window_metrics,
    detect_false_break,
    detect_sideways_state,
    detect_structural_escape,
)

PASS_SIDEWAYS_WIDE_RANGE = "PASS_SIDEWAYS_WIDE_RANGE"
PASS_FALSE_BREAK = "PASS_FALSE_BREAK"
WAIT_RANGE_ESCAPE = "WAIT_RANGE_ESCAPE"
TAKE_RANGE_ESCAPE = "TAKE_RANGE_ESCAPE"
TAKE_RANGE_ESCAPE_RETEST = "TAKE_RANGE_ESCAPE_RETEST"
TAKE_EXISTING_CONTINUATION = "TAKE_EXISTING_CONTINUATION"


@dataclass
class OverlayDecision:
    decision: str
    reason: str
    session: str
    existing: QualityDecision
    metrics: WindowMetrics | None
    sideways_wide_range: bool
    escape: EscapeResult | None
    false_break: bool
    market_state: str
    overlay_applied: bool

    def diagnostics(self) -> dict[str, object]:
        m = self.metrics
        e = self.escape
        return {
            "SESSION": self.session,
            "RANGE_ATR_20": None if m is None else round(m.range_atr_20, 4),
            "EFFICIENCY_20": None if m is None else round(m.directional_efficiency_20, 4),
            "OVERLAP_20": None if m is None else round(m.adjacent_overlap_ratio, 4),
            "NET_PROGRESS_20": None if m is None else round(m.net_progress_20, 4),
            "TOTAL_PATH_20": None if m is None else round(m.total_path_20, 4),
            "SIDEWAYS_STATE": self.market_state,
            "RANGE_UPPER": None if m is None else m.range_upper_prebreak,
            "RANGE_LOWER": None if m is None else m.range_lower_prebreak,
            "ESCAPE_DIR": "" if e is None else e.route,
            "CLOSE_THROUGH": False if e is None else e.close_through,
            "FALSE_BREAK": self.false_break,
            "RETEST_STATE": ""
            if e is None
            else ("hold" if e.retest_hold else "fail" if e.retest_fail else ""),
            "CONTINUATION_3_OF_4": False if m is None else m.continuation_3_of_4,
            "FINAL_DECISION": self.decision,
            "FINAL_REASON": self.reason,
        }


def _session_name(signal_time: datetime | None) -> str:
    if signal_time is None:
        return "unknown"
    return session_key_ny(signal_time)[1]


def evaluate_quality_with_sideways(
    bars: Sequence[Bar],
    direction: str,
    atr: float,
    signal_time: datetime | None = None,
    gate_cfg: QualityGateConfig | None = None,
    overlay_cfg: SidewaysOverlayConfig | None = None,
) -> OverlayDecision:
    gate_cfg = gate_cfg or QualityGateConfig()
    overlay_cfg = overlay_cfg or SidewaysOverlayConfig()
    existing = evaluate_quality_gates(bars, direction, atr, gate_cfg)
    session = _session_name(signal_time)
    metrics = compute_window_metrics(bars, direction, atr, overlay_cfg, gate_cfg)
    escape: EscapeResult | None = None
    false_brk = False
    sideways = False
    state = ""
    if metrics is not None:
        escape = detect_structural_escape(bars, direction, atr, metrics, overlay_cfg)
        false_brk = detect_false_break(metrics, direction)
        sideways = detect_sideways_state(metrics, overlay_cfg)
        state = classify_market_state(metrics, escape, false_brk, overlay_cfg)

    apply = overlay_cfg.enabled and (
        not overlay_cfg.apply_outside_rth_only or session == "globex"
    )

    def wrap(
        decision: str,
        reason: str,
        *,
        applied: bool,
    ) -> OverlayDecision:
        return OverlayDecision(
            decision=decision,
            reason=reason,
            session=session,
            existing=existing,
            metrics=metrics,
            sideways_wide_range=sideways,
            escape=escape,
            false_break=false_brk,
            market_state=state,
            overlay_applied=applied,
        )

    if not apply:
        return wrap(existing.decision, existing.reason, applied=False)

    if existing.reason == "SKIP_DATA":
        return wrap(existing.decision, existing.reason, applied=True)
    if existing.reason == "SKIP_CHOP":
        return wrap(existing.decision, existing.reason, applied=True)
    if existing.reason == "SKIP_ATR_CAP":
        return wrap(existing.decision, existing.reason, applied=True)

    if sideways and false_brk and escape is not None and not escape.valid:
        return wrap("SKIP", PASS_FALSE_BREAK, applied=True)
    if sideways and (escape is None or not escape.valid):
        if escape is not None and escape.retest_fail:
            return wrap("SKIP", PASS_FALSE_BREAK, applied=True)
        return wrap("SKIP", PASS_SIDEWAYS_WIDE_RANGE, applied=True)

    if sideways and escape is not None and escape.valid:
        if existing.decision != "TAKE":
            return wrap(existing.decision, existing.reason, applied=True)
        if escape.route == "retest":
            return wrap("TAKE", TAKE_RANGE_ESCAPE_RETEST, applied=True)
        return wrap("TAKE", TAKE_RANGE_ESCAPE, applied=True)

    if existing.decision == "TAKE" and metrics is not None and metrics.continuation_3_of_4:
        return wrap("TAKE", TAKE_EXISTING_CONTINUATION, applied=True)
    return wrap(existing.decision, existing.reason, applied=True)
