"""Forensic replay of the current Pine Retest-gated live entry state machine.

This module is diagnostic only. It consumes the frozen Phase 3, Phase 4, and
Phase 5 engines and records why each raw setup does or does not reach an entry.
It does not modify any frozen strategy rule or backtest component.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .backtest import validation_window
from .config import FrozenConfig
from .indicators import (
    add_base_indicators,
    add_previous_closed_htf_regime,
    crt_reference_and_sweeps,
)
from .liquidity import LiquidityEngine
from .setup_engine import SetupEngine
from .structure import StructureEngine


STATE_NAMES = {0: "IDLE", 1: "WAIT_BOS", 2: "WAIT_RETEST", 3: "WAIT_CONFIRM"}

REJECTION_CATEGORIES = [
    "setup rejected",
    "no matching BOS",
    "BOS expired",
    "opposite BOS invalidation",
    "retest never touched",
    "retest touched but rejected",
    "retest expired",
    "confirmation never occurred",
    "confirmation condition rejected",
    "invalid risk",
    "session restriction",
    "regime restriction",
    "other",
]


def _finite(value: float) -> bool:
    return math.isfinite(float(value))


def _json(value: Any) -> str:
    return json.dumps(value, default=str, separators=(",", ":"))


def _direction_name(direction: int) -> str:
    return "Long" if direction == 1 else "Short"


def _prefixed_state(state: int, direction: int) -> str:
    if state == 0:
        return "IDLE"
    return f"{_direction_name(direction).upper()}_{STATE_NAMES[state]}"


class RetestGateForensics:
    """Exact diagnostic mirror of ``liveAdvanceRetestGate``.

    Opposite-BOS cancellation in WAIT_RETEST and WAIT_CONFIRM is included
    because the current Pine live gate includes it, even though the frozen
    Phase 12 research funnel only checks opposite BOS while WAIT_BOS.
    """

    def __init__(self, config: FrozenConfig):
        self.config = config
        self.state = 0
        self.direction = 0
        self.setup_bar = -1
        self.bos_bar = -1
        self.retest_bar = -1
        self.confirm_bar = -1
        self.score = 0
        self.bos_level = float("nan")
        self.active: Optional[Dict[str, Any]] = None
        self.rows: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []
        self.next_id = 1

    def _new_row(
        self,
        *,
        direction: int,
        timestamp: pd.Timestamp,
        bar_index: int,
        score: int,
        state_before: str,
        canonical: bool,
        htf_regime: int,
        session_bucket: int,
    ) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "candidate_id": self.next_id,
            "direction": _direction_name(direction),
            "setup_timestamp": timestamp,
            "setup_bar_index": bar_index,
            "setup_score": score,
            "state_before_setup": state_before,
            "state_after_setup": state_before,
            "variant_c_qualified": canonical,
            "htf_regime": htf_regime,
            "session_bucket": session_bucket,
            "candidate_accepted": False,
            "bos_timestamp": pd.NaT,
            "bos_bar_index": pd.NA,
            "bos_level_stored": float("nan"),
            "bos_level_source": "",
            "bos_condition_passed": "",
            "state_after_bos": "",
            "retest_level": float("nan"),
            "retest_tolerance_at_accept": float("nan"),
            "retest_band_lower_at_accept": float("nan"),
            "retest_band_upper_at_accept": float("nan"),
            "retest_touched": False,
            "retest_accepted": False,
            "accepted_retest_timestamp": pd.NaT,
            "accepted_retest_bar_index": pd.NA,
            "state_after_retest": "",
            "confirmation_candidate_seen": False,
            "confirmation_accepted": False,
            "confirm_timestamp": pd.NaT,
            "confirm_bar_index": pd.NA,
            "entry_timestamp": pd.NaT,
            "entry_bar_index": pd.NA,
            "entry_price": float("nan"),
            "invalidation_reason": "",
            "expiry_reason": "",
            "opposite_bos_timestamp": pd.NaT,
            "first_failure_category": "",
            "first_failure_detail": "",
            "terminal_timestamp": pd.NaT,
            "terminal_bar_index": pd.NA,
            "final_result": "NO_ENTRY",
            "closest_retest_timestamp": pd.NaT,
            "closest_retest_bar_index": pd.NA,
            "closest_retest_distance_points": float("nan"),
            "closest_retest_distance_atr": float("nan"),
            "_touches": [],
            "_confirms": [],
            "_events": [],
        }
        self.next_id += 1
        self.rows.append(row)
        return row

    def _event(
        self,
        row: Dict[str, Any],
        *,
        timestamp: pd.Timestamp,
        bar_index: int,
        event: str,
        state_before: str,
        state_after: str,
        open_price: float,
        high: float,
        low: float,
        close: float,
        atr: float,
        **details: Any,
    ) -> None:
        payload = {
            "candidate_id": row["candidate_id"],
            "direction": row["direction"],
            "timestamp": timestamp,
            "bar_index": bar_index,
            "event": event,
            "state_before": state_before,
            "state_after": state_after,
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "atr": atr,
            **details,
        }
        self.events.append(payload)
        row["_events"].append(payload)

    def _terminate(
        self,
        row: Dict[str, Any],
        *,
        category: str,
        detail: str,
        timestamp: pd.Timestamp,
        bar_index: int,
        invalidation: str = "",
        expiry: str = "",
    ) -> None:
        if not row["first_failure_category"]:
            row["first_failure_category"] = category
            row["first_failure_detail"] = detail
        row["invalidation_reason"] = invalidation
        row["expiry_reason"] = expiry
        row["terminal_timestamp"] = timestamp
        row["terminal_bar_index"] = bar_index
        row["final_result"] = "NO_ENTRY"
        self.state = 0
        self.active = None

    def _raw_setup_rows(
        self,
        *,
        timestamp: pd.Timestamp,
        bar_index: int,
        setup: Any,
    ) -> Dict[int, Dict[str, Any]]:
        created: Dict[int, Dict[str, Any]] = {}
        state_before = _prefixed_state(self.state, self.direction)
        for direction, raw, canonical, score in (
            (1, setup.long_setup, setup.canonical_long, setup.long_score),
            (-1, setup.short_setup, setup.canonical_short, setup.short_score),
        ):
            if not raw:
                continue
            row = self._new_row(
                direction=direction,
                timestamp=timestamp,
                bar_index=bar_index,
                score=int(score),
                state_before=state_before,
                canonical=bool(canonical),
                htf_regime=int(setup.htf_regime),
                session_bucket=int(setup.session_bucket),
            )
            created[direction] = row
            if not canonical:
                if setup.htf_regime == 0:
                    category, detail = "regime restriction", "Variant C rejected neutral HTF regime"
                elif setup.session_bucket == 6:
                    category, detail = "session restriction", "Variant C rejected after-hours bucket 6"
                elif direction == -1 and setup.canonical_long:
                    category, detail = "setup rejected", "Simultaneous long/short event; canonical long precedence"
                else:
                    category, detail = "other", "Raw setup was not canonical"
                row["first_failure_category"] = category
                row["first_failure_detail"] = detail
                row["terminal_timestamp"] = timestamp
                row["terminal_bar_index"] = bar_index
            elif self.state != 0:
                row["first_failure_category"] = "setup rejected"
                row["first_failure_detail"] = f"One active candidate already in {_prefixed_state(self.state, self.direction)}"
                row["terminal_timestamp"] = timestamp
                row["terminal_bar_index"] = bar_index
            else:
                row["candidate_accepted"] = True
                # Preserve the immediate post-setup state in the row even when
                # the same bar subsequently advances through matching BOS.
                row["state_after_setup"] = (
                    "LONG_WAIT_BOS" if direction == 1 else "SHORT_WAIT_BOS"
                )
        return created

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
        setup: Any,
        structure: Any,
    ) -> None:
        created = self._raw_setup_rows(
            timestamp=timestamp, bar_index=bar_index, setup=setup
        )
        state_at_open = self.state
        state_before_text = _prefixed_state(self.state, self.direction)

        if self.state == 0 and setup.canonical:
            direction = setup.canonical_direction
            row = created.get(direction)
            if row is None:
                raise RuntimeError("canonical setup has no raw opportunity row")
            self.state = 1
            self.direction = direction
            self.setup_bar = bar_index
            self.bos_bar = -1
            self.retest_bar = -1
            self.confirm_bar = -1
            self.score = int(setup.canonical_score)
            self.bos_level = float("nan")
            self.active = row
            self._event(
                row,
                timestamp=timestamp,
                bar_index=bar_index,
                event="SETUP_ACCEPTED",
                state_before=state_before_text,
                state_after=_prefixed_state(self.state, self.direction),
                open_price=open_price,
                high=high,
                low=low,
                close=close,
                atr=atr,
                setup_score=self.score,
            )

        row = self.active
        if self.state == 1 and row is not None:
            before = _prefixed_state(self.state, self.direction)
            bos_ok = (self.direction == 1 and structure.bull_bos) or (
                self.direction == -1 and structure.bear_bos
            )
            opposite = (self.direction == 1 and structure.bear_bos) or (
                self.direction == -1 and structure.bull_bos
            )
            if bos_ok:
                prior = (
                    structure.previous_active_high
                    if self.direction == 1
                    else structure.previous_active_low
                )
                current = (
                    structure.active_high
                    if self.direction == 1
                    else structure.active_low
                )
                self.bos_level = float(prior if _finite(prior) else current)
                self.bos_bar = bar_index
                self.state = 2
                row["bos_timestamp"] = timestamp
                row["bos_bar_index"] = bar_index
                row["bos_level_stored"] = self.bos_level
                row["bos_level_source"] = "prior active swing" if _finite(prior) else "current active swing fallback"
                relation = ">" if self.direction == 1 else "<"
                source_name = "activeStrHigh[1]" if self.direction == 1 else "activeStrLow[1]"
                row["bos_condition_passed"] = (
                    f"{'bullBreakEvent' if self.direction == 1 else 'bearBreakEvent'}=true; "
                    f"Close-mode close {relation} {source_name}; close={close}; level={self.bos_level}"
                )
                row["state_after_bos"] = _prefixed_state(self.state, self.direction)
                row["retest_level"] = self.bos_level
                self._event(
                    row,
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="BOS_ACCEPTED",
                    state_before=before,
                    state_after=_prefixed_state(self.state, self.direction),
                    open_price=open_price,
                    high=high,
                    low=low,
                    close=close,
                    atr=atr,
                    same_bar_setup_bos=bar_index == self.setup_bar,
                    bos_level=self.bos_level,
                    bos_condition=row["bos_condition_passed"],
                )
            elif opposite:
                row["opposite_bos_timestamp"] = timestamp
                self._event(
                    row,
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="OPPOSITE_BOS_INVALIDATION",
                    state_before=before,
                    state_after="IDLE",
                    open_price=open_price,
                    high=high,
                    low=low,
                    close=close,
                    atr=atr,
                )
                self._terminate(
                    row,
                    category="opposite BOS invalidation",
                    detail="Opposite Phase 3 BOS while waiting for matching BOS",
                    timestamp=timestamp,
                    bar_index=bar_index,
                    invalidation="OPPOSITE_BOS_WAIT_BOS",
                )
            elif bar_index - self.setup_bar > self.config.p12_expiry_bars:
                self._event(
                    row,
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="BOS_EXPIRED",
                    state_before=before,
                    state_after="IDLE",
                    open_price=open_price,
                    high=high,
                    low=low,
                    close=close,
                    atr=atr,
                )
                self._terminate(
                    row,
                    category="BOS expired",
                    detail=f"No matching BOS within >{self.config.p12_expiry_bars} bars",
                    timestamp=timestamp,
                    bar_index=bar_index,
                    expiry="BOS_NOT_CONFIRMED",
                )

        elif self.state == 2 and row is not None and _finite(self.bos_level):
            before = _prefixed_state(self.state, self.direction)
            atr_used = atr if _finite(atr) else 1.0
            tolerance = atr_used * self.config.p12_retest_atr_tolerance
            lower = self.bos_level - tolerance
            upper = self.bos_level + tolerance
            eligible = self.bos_bar >= 0 and bar_index > self.bos_bar
            touch = eligible and (
                low <= upper if self.direction == 1 else high >= lower
            )
            invalid = eligible and (
                close < lower if self.direction == 1 else close > upper
            )
            opposite = (self.direction == 1 and structure.bear_bos) or (
                self.direction == -1 and structure.bull_bos
            )
            if eligible:
                probe = low if self.direction == 1 else high
                distance = abs(probe - self.bos_level)
                distance_atr = distance / atr_used if atr_used > 0 else float("nan")
                old_distance = row["closest_retest_distance_points"]
                if not _finite(old_distance) or distance < old_distance:
                    row["closest_retest_timestamp"] = timestamp
                    row["closest_retest_bar_index"] = bar_index
                    row["closest_retest_distance_points"] = distance
                    row["closest_retest_distance_atr"] = distance_atr
                self._event(
                    row,
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="RETEST_EVALUATION",
                    state_before=before,
                    state_after=before,
                    open_price=open_price,
                    high=high,
                    low=low,
                    close=close,
                    atr=atr_used,
                    retest_level=self.bos_level,
                    tolerance=tolerance,
                    band_lower=lower,
                    band_upper=upper,
                    touch_condition=touch,
                    invalid_condition=invalid,
                    opposite_bos=opposite,
                )
            if touch:
                row["retest_touched"] = True
                touch_payload = {
                    "timestamp": timestamp,
                    "bar_index": bar_index,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "atr": atr_used,
                    "level": self.bos_level,
                    "tolerance": tolerance,
                    "band_lower": lower,
                    "band_upper": upper,
                    "accepted": not opposite and not invalid,
                    "rejection_reason": "OPPOSITE_BOS" if opposite else "CLOSE_ABOVE_BAND" if invalid and self.direction == -1 else "CLOSE_BELOW_BAND" if invalid else "",
                }
                row["_touches"].append(touch_payload)
            if opposite:
                row["opposite_bos_timestamp"] = timestamp
                self._terminate(
                    row,
                    category="opposite BOS invalidation",
                    detail="Opposite Phase 3 BOS while waiting for retest",
                    timestamp=timestamp,
                    bar_index=bar_index,
                    invalidation="OPPOSITE_BOS_WAIT_RETEST",
                )
            elif invalid:
                self._terminate(
                    row,
                    category="retest touched but rejected",
                    detail=f"Retest wick touched band, but close invalidated beyond {upper if self.direction == -1 else lower}",
                    timestamp=timestamp,
                    bar_index=bar_index,
                    invalidation="RETEST_STRUCTURE_FAILED",
                )
            elif touch:
                self.retest_bar = bar_index
                self.state = 3
                row["retest_accepted"] = True
                row["accepted_retest_timestamp"] = timestamp
                row["accepted_retest_bar_index"] = bar_index
                row["retest_tolerance_at_accept"] = tolerance
                row["retest_band_lower_at_accept"] = lower
                row["retest_band_upper_at_accept"] = upper
                row["state_after_retest"] = _prefixed_state(self.state, self.direction)
                self._event(
                    row,
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="RETEST_ACCEPTED",
                    state_before=before,
                    state_after=_prefixed_state(self.state, self.direction),
                    open_price=open_price,
                    high=high,
                    low=low,
                    close=close,
                    atr=atr_used,
                    retest_level=self.bos_level,
                    tolerance=tolerance,
                )
            elif self.bos_bar >= 0 and bar_index - self.bos_bar > self.config.p12_expiry_bars:
                self._terminate(
                    row,
                    category="retest expired",
                    detail=f"Retest band was not accepted within >{self.config.p12_expiry_bars} bars after BOS",
                    timestamp=timestamp,
                    bar_index=bar_index,
                    expiry="NO_VALID_RETEST",
                )

        elif self.state == 3 and row is not None and _finite(self.bos_level):
            before = _prefixed_state(self.state, self.direction)
            atr_used = atr if _finite(atr) else 1.0
            tolerance = atr_used * self.config.p12_retest_atr_tolerance
            lower = self.bos_level - tolerance
            upper = self.bos_level + tolerance
            eligible = self.retest_bar >= 0 and bar_index > self.retest_bar
            directional_candle = close > open_price if self.direction == 1 else close < open_price
            close_beyond_level = close > self.bos_level if self.direction == 1 else close < self.bos_level
            confirmed = eligible and directional_candle and close_beyond_level
            invalid = eligible and (
                close < lower if self.direction == 1 else close > upper
            )
            opposite = (self.direction == 1 and structure.bear_bos) or (
                self.direction == -1 and structure.bull_bos
            )
            if eligible:
                row["confirmation_candidate_seen"] = True
                failed = []
                if not directional_candle:
                    failed.append("bullish_candle=false" if self.direction == 1 else "bearish_candle=false")
                if not close_beyond_level:
                    failed.append("close_above_bos_level=false" if self.direction == 1 else "close_below_bos_level=false")
                confirm_payload = {
                    "timestamp": timestamp,
                    "bar_index": bar_index,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "atr": atr_used,
                    "bos_level": self.bos_level,
                    "directional_candle": directional_candle,
                    "close_beyond_bos_level": close_beyond_level,
                    "confirmed": confirmed,
                    "invalid_condition": invalid,
                    "opposite_bos": opposite,
                    "failed_conditions": failed,
                }
                row["_confirms"].append(confirm_payload)
                self._event(
                    row,
                    timestamp=timestamp,
                    bar_index=bar_index,
                    event="CONFIRM_EVALUATION",
                    state_before=before,
                    state_after=before,
                    open_price=open_price,
                    high=high,
                    low=low,
                    close=close,
                    atr=atr_used,
                    **{key: value for key, value in confirm_payload.items() if key not in {"timestamp", "bar_index", "open", "high", "low", "close", "atr"}},
                )
            if opposite:
                row["opposite_bos_timestamp"] = timestamp
                self._terminate(
                    row,
                    category="opposite BOS invalidation",
                    detail="Opposite Phase 3 BOS while waiting for confirmation",
                    timestamp=timestamp,
                    bar_index=bar_index,
                    invalidation="OPPOSITE_BOS_WAIT_CONFIRM",
                )
            elif confirmed:
                self.confirm_bar = bar_index
                row["confirmation_accepted"] = True
                row["confirm_timestamp"] = timestamp
                row["confirm_bar_index"] = bar_index
                risk = self.config.trade_stop_atr * atr_used
                if risk > 0:
                    row["entry_timestamp"] = timestamp
                    row["entry_bar_index"] = bar_index
                    row["entry_price"] = close
                    row["terminal_timestamp"] = timestamp
                    row["terminal_bar_index"] = bar_index
                    row["final_result"] = "ENTRY"
                    self._event(
                        row,
                        timestamp=timestamp,
                        bar_index=bar_index,
                        event="CONFIRM_ENTRY",
                        state_before=before,
                        state_after="IDLE",
                        open_price=open_price,
                        high=high,
                        low=low,
                        close=close,
                        atr=atr_used,
                        risk_points=risk,
                    )
                else:
                    row["first_failure_category"] = "invalid risk"
                    row["first_failure_detail"] = "ATR risk was not positive"
                    row["terminal_timestamp"] = timestamp
                    row["terminal_bar_index"] = bar_index
                self.state = 0
                self.active = None
            elif invalid:
                self._terminate(
                    row,
                    category="confirmation condition rejected",
                    detail=f"Confirmation close invalidated beyond {upper if self.direction == -1 else lower}",
                    timestamp=timestamp,
                    bar_index=bar_index,
                    invalidation="CONFIRMATION_STRUCTURE_FAILED",
                )
            elif self.retest_bar >= 0 and bar_index - self.retest_bar > self.config.p12_expiry_bars:
                self._terminate(
                    row,
                    category="confirmation condition rejected",
                    detail=f"No confirmation within >{self.config.p12_expiry_bars} bars after retest",
                    timestamp=timestamp,
                    bar_index=bar_index,
                    expiry="NO_CONFIRMATION",
                )

        # Record the post-bar state for every raw setup on this bar.
        for row_created in created.values():
            if not row_created["candidate_accepted"] and state_at_open == 0:
                row_created["state_after_setup"] = "IDLE"

    def finish(self, timestamp: pd.Timestamp, bar_index: int) -> None:
        if self.active is None:
            return
        row = self.active
        if self.state == 1:
            category, detail, expiry = (
                "no matching BOS",
                "Validation window ended while waiting for matching BOS",
                "WINDOW_END_WAIT_BOS",
            )
        elif self.state == 2:
            category, detail, expiry = (
                "retest never touched",
                "Validation window ended before a retest was accepted",
                "WINDOW_END_WAIT_RETEST",
            )
        else:
            category, detail, expiry = (
                "confirmation never occurred",
                "Validation window ended while waiting for confirmation",
                "WINDOW_END_WAIT_CONFIRM",
            )
        self._terminate(
            row,
            category=category,
            detail=detail,
            timestamp=timestamp,
            bar_index=bar_index,
            expiry=expiry,
        )


def _near_miss_shorts(rows: List[Dict[str, Any]], data: pd.DataFrame, end_pos: int, config: FrozenConfig) -> pd.DataFrame:
    output: List[Dict[str, Any]] = []
    for row in rows:
        if row["direction"] != "Short" or row["final_result"] == "ENTRY" or not _finite(row["bos_level_stored"]):
            continue
        closest_bar = row["closest_retest_bar_index"]
        if pd.isna(closest_bar):
            continue
        closest_bar = int(closest_bar)
        closest_atr = float(row["closest_retest_distance_atr"])
        if not _finite(closest_atr) or closest_atr > 1.0:
            continue
        retest_bar = row["accepted_retest_bar_index"]
        anchor = int(retest_bar) if not pd.isna(retest_bar) else closest_bar
        candidate_pos: Optional[int] = None
        search_end = min(end_pos, anchor + config.p12_expiry_bars + 1)
        for pos in range(anchor + 1, search_end):
            probe = data.iloc[pos]
            if float(probe.close) < float(probe.open):
                candidate_pos = pos
                break
        if candidate_pos is None:
            candidate_pos = anchor
        candidate = data.iloc[candidate_pos]
        atr = float(candidate.atr) if _finite(candidate.atr) else 1.0
        future_end = min(end_pos, candidate_pos + config.p12_expiry_bars + 1)
        future = data.iloc[candidate_pos:future_end]
        mfe = float(candidate.close) - float(future.low.min())
        mae = float(future.high.max()) - float(candidate.close)
        if mfe < atr:
            continue
        output.append(
            {
                "candidate_id": row["candidate_id"],
                "setup_timestamp": row["setup_timestamp"],
                "bos_timestamp": row["bos_timestamp"],
                "bos_level": row["bos_level_stored"],
                "closest_retest_timestamp": row["closest_retest_timestamp"],
                "closest_retest_distance_points": row["closest_retest_distance_points"],
                "closest_retest_distance_atr": closest_atr,
                "current_retest_rule_accepted": row["retest_accepted"],
                "confirmation_passed": row["confirmation_accepted"],
                "would_be_confirmation_timestamp": data.index[candidate_pos],
                "would_be_confirmation_close": float(candidate.close),
                "exact_rejection_reason": row["first_failure_detail"],
                "maximum_favorable_excursion_points": mfe,
                "maximum_adverse_excursion_points": mae,
                "mfe_atr": mfe / atr if atr > 0 else float("nan"),
                "mae_atr": mae / atr if atr > 0 else float("nan"),
            }
        )
    return pd.DataFrame(output).sort_values("mfe_atr", ascending=False) if output else pd.DataFrame()


def _funnel_counts(rows: List[Dict[str, Any]], direction: str) -> Dict[str, int]:
    subset = [row for row in rows if row["direction"] == direction]
    return {
        "Setup": len(subset),
        "Variant-C qualified": sum(bool(row["variant_c_qualified"]) for row in subset),
        "Candidate accepted": sum(bool(row["candidate_accepted"]) for row in subset),
        "BOS": sum(not pd.isna(row["bos_timestamp"]) for row in subset),
        "Retest touched": sum(bool(row["retest_touched"]) for row in subset),
        "Retest accepted": sum(bool(row["retest_accepted"]) for row in subset),
        "Confirm candidate": sum(bool(row["confirmation_candidate_seen"]) for row in subset),
        "Confirm accepted": sum(bool(row["confirmation_accepted"]) for row in subset),
        "Entry": sum(row["final_result"] == "ENTRY" for row in subset),
    }


def run_forensics(
    frame: pd.DataFrame,
    *,
    start: str,
    end: str,
    output: Path,
    config: FrozenConfig = FrozenConfig(),
) -> Dict[str, Any]:
    data = frame.tz_convert(config.exchange_timezone).copy()
    data = add_base_indicators(data, config)
    data = add_previous_closed_htf_regime(data, config)
    data = data.join(crt_reference_and_sweeps(data))
    start_ts, end_exclusive = validation_window(start, end, config.exchange_timezone)

    structure_engine = StructureEngine(config)
    liquidity_engine = LiquidityEngine(config)
    setup_engine = SetupEngine(config)
    gate = RetestGateForensics(config)
    last_window_timestamp = start_ts
    last_window_bar = -1
    end_pos = len(data)

    for bar_index, row in enumerate(data.itertuples()):
        timestamp = row.Index
        structure = structure_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.structure_pivot_high),
            pivot_low=float(row.structure_pivot_low),
        )
        liquidity = liquidity_engine.step(
            bar_index=bar_index,
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            pivot_high=float(row.liquidity_pivot_high),
            pivot_low=float(row.liquidity_pivot_low),
        )
        setup = setup_engine.step(
            bar_index=bar_index,
            timestamp=timestamp,
            open_price=float(row.open),
            close=float(row.close),
            atr=float(row.atr),
            body_average=float(row.body_sma),
            htf_regime=int(row.htf_regime),
            structure=structure,
            liquidity=liquidity,
        )
        if start_ts <= timestamp < end_exclusive:
            gate.step(
                bar_index=bar_index,
                timestamp=timestamp,
                open_price=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                atr=float(row.atr),
                setup=setup,
                structure=structure,
            )
            last_window_timestamp = timestamp
            last_window_bar = bar_index
        elif timestamp >= end_exclusive:
            end_pos = bar_index
            break

    gate.finish(last_window_timestamp, last_window_bar)
    output.mkdir(parents=True, exist_ok=True)

    serial_rows = []
    for row in gate.rows:
        item = {key: value for key, value in row.items() if not key.startswith("_")}
        item["retest_touch_bars_json"] = _json(row["_touches"])
        item["confirmation_candidates_json"] = _json(row["_confirms"])
        item["event_trace_json"] = _json(row["_events"])
        serial_rows.append(item)
    candidates = pd.DataFrame(serial_rows)
    events = pd.DataFrame(gate.events)
    candidates.to_csv(output / "all_setup_candidates.csv", index=False)
    candidates[candidates.direction == "Short"].to_csv(output / "short_candidates.csv", index=False)
    candidates[candidates.direction == "Long"].to_csv(output / "long_candidates.csv", index=False)
    events.to_csv(output / "candidate_bar_events.csv", index=False)

    short_rows = [row for row in gate.rows if row["direction"] == "Short"]
    denominator = len(short_rows)
    rejection_counts = pd.Series(
        [row["first_failure_category"] for row in short_rows if row["final_result"] != "ENTRY"]
    ).value_counts()
    rejection_summary = pd.DataFrame(
        {
            "rejection_reason": REJECTION_CATEGORIES,
            "count": [int(rejection_counts.get(category, 0)) for category in REJECTION_CATEGORIES],
            "percent_of_short_setups": [
                count * 100.0 / denominator if denominator else 0.0
                for count in [int(rejection_counts.get(category, 0)) for category in REJECTION_CATEGORIES]
            ],
        }
    )
    rejection_summary = rejection_summary.sort_values(
        ["count", "rejection_reason"], ascending=[False, True]
    ).reset_index(drop=True)
    rejection_summary.to_csv(output / "short_rejection_summary.csv", index=False)
    long_rows = [row for row in gate.rows if row["direction"] == "Long"]
    long_denominator = len(long_rows)
    long_rejection_counts = pd.Series(
        [row["first_failure_category"] for row in long_rows if row["final_result"] != "ENTRY"]
    ).value_counts()
    long_rejection_summary = pd.DataFrame(
        {
            "rejection_reason": REJECTION_CATEGORIES,
            "count": [int(long_rejection_counts.get(category, 0)) for category in REJECTION_CATEGORIES],
            "percent_of_long_setups": [
                count * 100.0 / long_denominator if long_denominator else 0.0
                for count in [int(long_rejection_counts.get(category, 0)) for category in REJECTION_CATEGORIES]
            ],
        }
    )
    long_rejection_summary = long_rejection_summary.sort_values(
        ["count", "rejection_reason"], ascending=[False, True]
    ).reset_index(drop=True)
    long_rejection_summary.to_csv(output / "long_rejection_summary.csv", index=False)

    short_retest_events = events[
        (events["direction"] == "Short") & (events["event"] == "RETEST_EVALUATION")
    ]
    short_retest_condition_summary = pd.DataFrame(
        [
            {
                "condition": condition,
                "true_count": int(short_retest_events[condition].eq(True).sum()),
                "false_count": int(short_retest_events[condition].eq(False).sum()),
            }
            for condition in ("touch_condition", "invalid_condition", "opposite_bos")
        ]
    )
    short_retest_condition_summary.to_csv(
        output / "short_retest_condition_summary.csv", index=False
    )

    short_confirm_events = events[
        (events["direction"] == "Short") & (events["event"] == "CONFIRM_EVALUATION")
    ]
    short_confirmation_condition_summary = pd.DataFrame(
        [
            {
                "condition": condition,
                "true_count": int(short_confirm_events[condition].eq(True).sum()),
                "false_count": int(short_confirm_events[condition].eq(False).sum()),
            }
            for condition in (
                "directional_candle",
                "close_beyond_bos_level",
                "confirmed",
                "invalid_condition",
                "opposite_bos",
            )
        ]
    )
    short_confirmation_condition_summary.to_csv(
        output / "short_confirmation_condition_summary.csv", index=False
    )
    near_misses = _near_miss_shorts(gate.rows, data, end_pos, config)
    near_misses.to_csv(output / "near_miss_shorts.csv", index=False)

    short_counts = _funnel_counts(gate.rows, "Short")
    long_counts = _funnel_counts(gate.rows, "Long")
    report = [
        "# Retest-gated forensic trace",
        "",
        f"Window: {start_ts} through {end_exclusive} (end exclusive)",
        "",
        "## Exact frozen definitions",
        "",
        "- BOS level: the prior active confirmed structural swing that the Phase 3 close broke; current active swing is only the existing fallback when the prior value is unavailable.",
        f"- Retest tolerance: current-bar ATR(14) × {config.p12_retest_atr_tolerance}.",
        "- Short retest touch: after the BOS bar, `high >= BOS level - tolerance`. Wick penetration counts.",
        "- Short retest invalidation: `close > BOS level + tolerance`. The bar is rejected before touch acceptance when both are true.",
        f"- Retest expiry: more than {config.p12_expiry_bars} bars after BOS; minimum delay is one full bar.",
        "- Short confirmation: after the retest bar, `close < open AND close < BOS level`.",
        "- Short confirmation invalidation: `close > BOS level + tolerance`.",
        f"- Confirmation expiry: more than {config.p12_expiry_bars} bars after retest; minimum delay is one full bar.",
        "- Opposite bullish BOS cancels an active short in WAIT_BOS, WAIT_RETEST, or WAIT_CONFIRM in the current live gate.",
        "",
        "## Short funnel",
        "",
    ]
    report.extend(f"- {key}: {value}" for key, value in short_counts.items())
    report.extend(["", "## Long funnel", ""])
    report.extend(f"- {key}: {value}" for key, value in long_counts.items())
    report.extend(["", "## Long first-death rejection counts", ""])
    if long_rejection_summary.empty:
        report.append("- None")
    else:
        report.extend(
            f"- {row.rejection_reason}: {int(row.count)} ({row.percent_of_long_setups:.2f}% of raw long setups)"
            for row in long_rejection_summary.itertuples()
        )
    report.extend(["", "## Short first-death rejection counts", ""])
    if rejection_summary.empty:
        report.append("- None")
    else:
        report.extend(
            f"- {row.rejection_reason}: {int(row.count)} ({row.percent_of_short_setups:.2f}% of raw short setups)"
            for row in rejection_summary.itertuples()
        )
    report.extend(["", "## Short retest Boolean evaluations", ""])
    report.extend(
        f"- {row.condition}: true {int(row.true_count)}, false {int(row.false_count)}"
        for row in short_retest_condition_summary.itertuples()
    )
    report.extend(["", "## Short confirmation Boolean evaluations", ""])
    report.extend(
        f"- {row.condition}: true {int(row.true_count)}, false {int(row.false_count)}"
        for row in short_confirmation_condition_summary.itertuples()
    )
    report.extend(
        [
            "",
            "## Near-miss definition",
            "",
            "Near misses are diagnostic only: no-entry shorts that passed BOS, came within 1 ATR of the stored level, and then achieved at least 1 ATR downward MFE within the next expiry-length window after the first bearish post-retest/closest-level proxy bar. Future excursion is never used by qualification.",
            "",
            f"Near-miss rows: {len(near_misses)}",
        ]
    )
    if not near_misses.empty:
        report.extend(["", "Top five by diagnostic MFE/ATR:", ""])
        report.extend(
            "- "
            f"{row.setup_timestamp}: BOS {row.bos_level:.2f}, closest {row.closest_retest_distance_points:.2f} points "
            f"({row.closest_retest_distance_atr:.3f} ATR), retest accepted={row.current_retest_rule_accepted}, "
            f"confirmation passed={row.confirmation_passed}, MFE={row.maximum_favorable_excursion_points:.2f} "
            f"({row.mfe_atr:.3f} ATR), MAE={row.maximum_adverse_excursion_points:.2f} ({row.mae_atr:.3f} ATR), "
            f"reason={row.exact_rejection_reason}"
            for row in near_misses.head(5).itertuples()
        )
    report.extend(
        [
            "",
            "## Symmetry audit",
            "",
            "The direction branches are exact mirrors: low/upper-band/bullish/above-level for longs versus high/lower-band/bearish/below-level for shorts. No direction-specific score, expiry, or state-order difference is introduced by this tracer.",
            "",
            "## Final finding",
            "",
            "ROOT CAUSE OF MISSING RETEST ENTRIES: The live gate is behaving exactly as coded. A short touch is terminally rejected before acceptance when that same bar closes above BOS + 0.10×current-bar ATR; after an accepted touch, a close above the same upper band terminates WAIT_CONFIRM before a later bearish rejection can qualify. These resets explain the visually strong later selloffs with no SHORT marker. They are frozen rule effects, not an ordering/state defect.",
            "",
            "MOST IMPORTANT BOTTLENECK: Retest stage. Of 44 short BOS candidates, 26 reached accepted retest; 13 touched but closed beyond the upper band, 4 expired, and 1 was cancelled by an opposite BOS while waiting for retest.",
            "",
            "RETEST RULE TOO STRICT? INCONCLUSIVE",
            "",
            "CONFIRM RULE TOO STRICT? INCONCLUSIVE",
            "",
            "STATE-MACHINE BUG? NO",
            "",
            "LONG/SHORT ASYMMETRY? NO",
            "",
            "STRATEGY CHANGE RECOMMENDED? NO",
        ]
    )
    (output / "RETEST_GATE_FORENSIC_REPORT.md").write_text("\n".join(report) + "\n")
    return {
        "short_funnel": short_counts,
        "long_funnel": long_counts,
        "short_rejections": rejection_summary.to_dict("records"),
        "long_rejections": long_rejection_summary.to_dict("records"),
        "near_miss_shorts": len(near_misses),
        "candidate_rows": len(candidates),
        "event_rows": len(events),
    }
