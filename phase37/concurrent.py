"""Concurrent reversal candidate engine — causal multi-tracker matching Phase 33 batch."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session
from phase16.resample import cme_session_date

from phase36.replay import (
    ContinuationMachine,
    DedupeTracker,
    _close_loc,
    _try_bos_retest_fill,
)
from phase36.config import (
    BOS_RETEST_TOL_ATR,
    P31_BODY_AVG_LEN,
    P31_BODY_MULT,
    P31_BOS_RETEST_WIN,
    P31_CL_LONG,
    P31_CL_SHORT,
    P31_MAX_HOLD_BARS,
    P31_STOP_ATR,
    P31_TARGET_R,
    P33_MAX_HOLD_BARS,
    P33_STOP_ATR,
    P33_TARGET_R,
    RTH_SESSION,
)

from .config import (
    DEDUPE_ACTIVE_BARS,
    DEDUPE_DAY_CAP,
    DEDUPE_MAX_HOLD_BARS,
    DEDUPE_SAME_DIR,
    P33_FAILURE_WIN,
    P33_RETEST_WIN,
)


def _day_key(ts: pd.Timestamp) -> str:
    return str(cme_session_date(pd.DatetimeIndex([ts]))[0])


def _rev_direction(disp_dir: str) -> str:
    return "Long" if disp_dir == "Short" else "Short"


def _midpoint_reclaimed(disp_dir: str, mid: float, close: float) -> bool:
    """Match phase33.failure._reclaim_hit at midpoint."""
    if disp_dir == "Short":
        return close > mid
    return close < mid


def _rev_dir_code(disp_dir: str) -> int:
    return 1 if disp_dir == "Short" else -1



@dataclass
class ReversalCandidate:
    candidate_id: int
    displacement_id: int
    disp_bar: int
    disp_ts: pd.Timestamp
    disp_dir: str
    rev_dir: str
    disp_high: float
    disp_low: float
    midpoint: float
    expiry_bar: int
    state: str = "WAIT_FOR_RECLAIM"
    reclaim_bar: int = -1
    reclaim_ts: Optional[pd.Timestamp] = None
    reclaim_level: float = np.nan
    retest_deadline: int = -1
    tol: float = np.nan
    dedupe_passed: bool = False
    event_id: str = ""
    fill_bar: int = -1
    fill_ts: Optional[pd.Timestamp] = None
    entry_price: float = np.nan
    stop: float = np.nan
    target: float = np.nan


@dataclass
class ReversalDedupeState:
    """Phase 33 batch dedupe semantics — applied at reclaim (confirm) bar, not displacement."""

    active_until: int = -1
    last_long: int = -999
    last_short: int = -999
    day_key: str = ""
    day_count: int = 0
    seen_events: set = field(default_factory=set)

    def reset_day(self, ts: pd.Timestamp) -> None:
        dk = _day_key(ts)
        if dk != self.day_key:
            self.day_key = dk
            self.day_count = 0

    def try_keep(self, *, bar_i: int, direction: str, event_id: str, ts: pd.Timestamp) -> bool:
        """Return True if candidate passes Phase 33 dedupe at reclaim bar."""
        self.reset_day(ts)
        if event_id in self.seen_events:
            return False
        dcode = 1 if direction == "Long" else -1
        same_dir_ok = (
            bar_i - self.last_long >= DEDUPE_SAME_DIR
            if dcode == 1
            else bar_i - self.last_short >= DEDUPE_SAME_DIR
        )
        if not (bar_i > self.active_until and same_dir_ok and self.day_count < DEDUPE_DAY_CAP):
            return False
        self.seen_events.add(event_id)
        if dcode == 1:
            self.last_long = bar_i
        else:
            self.last_short = bar_i
        self.day_count += 1
        self.active_until = bar_i + DEDUPE_MAX_HOLD_BARS
        return True


def _detect_displacement(
    i: int,
    ts: pd.Timestamp,
    row,
    *,
    body: float,
    avg_body: float,
    cl: float,
    rth: bool,
    body_ready: bool,
) -> Optional[str]:
    if not (rth and body_ready and body > P31_BODY_MULT * avg_body):
        return None
    if cl >= P31_CL_LONG:
        return "Long"
    if cl <= P31_CL_SHORT:
        return "Short"
    return None


def replay_concurrent(market: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Full-history replay: frozen Phase 31 continuation + concurrent Phase 33 reversal.

    Returns (combined_signals, candidate_log, bar_state_log).
    """
    idx = market.index
    n = len(market)
    body_s = (market["close"] - market["open"]).abs()
    avg_body = body_s.rolling(P31_BODY_AVG_LEN, min_periods=P31_BODY_AVG_LEN).mean()

    p31 = ContinuationMachine()
    active: List[ReversalCandidate] = []
    rev_dedupe = ReversalDedupeState()
    disp_count = 0
    cand_count = 0
    signals: List[dict] = []
    candidate_rows: List[dict] = []
    state_rows: List[dict] = []
    signal_id = 0
    concurrency_samples: List[int] = []

    for i in range(n):
        ts = idx[i]
        row = market.iloc[i]
        rth = is_in_session(ts, RTH_SESSION)
        atr = float(row["atr"]) if np.isfinite(row["atr"]) else np.nan
        cl = _close_loc(row)
        b = float(body_s.iloc[i])
        ab = float(avg_body.iloc[i]) if i >= P31_BODY_AVG_LEN - 1 and np.isfinite(avg_body.iloc[i]) else np.nan
        body_ready = i >= P31_BODY_AVG_LEN - 1 and np.isfinite(ab)
        disp_dir = _detect_displacement(i, ts, row, body=b, avg_body=ab, cl=cl, rth=rth, body_ready=body_ready)

        l_fire = s_fire = rl_fire = rs_fire = False
        fire_entry = fire_stop = fire_target = np.nan
        fire_type = ""

        # ── Phase 31 continuation (frozen, unchanged) ──
        if p31.state == "ACTIVE":
            p31.held += 1
            hit_stop = (p31.direction == 1 and float(row.low) <= p31.stop) or (
                p31.direction == -1 and float(row.high) >= p31.stop
            )
            hit_tgt = (p31.direction == 1 and float(row.high) >= p31.target) or (
                p31.direction == -1 and float(row.low) <= p31.target
            )
            if hit_stop or hit_tgt or p31.held >= P31_MAX_HOLD_BARS:
                p31.state = "IDLE"
                p31.direction = 0
        elif p31.state == "WAIT":
            if i > p31.deadline:
                p31.state = "IDLE"
                p31.direction = 0
            elif i > p31.disp_bar:
                filled, px = _try_bos_retest_fill(p31.direction, p31.bos_level, p31.tol, row)
                if filled:
                    risk = P31_STOP_ATR * atr
                    p31.entry_price = px
                    p31.stop = px - risk if p31.direction == 1 else px + risk
                    p31.target = px + P31_TARGET_R * risk if p31.direction == 1 else px - P31_TARGET_R * risk
                    p31.held = 0
                    p31.state = "ACTIVE"
                    signal_id += 1
                    sig_type = "L" if p31.direction == 1 else "S"
                    l_fire = p31.direction == 1
                    s_fire = p31.direction == -1
                    fire_type = sig_type
                    fire_entry = px
                    fire_stop = p31.stop
                    fire_target = p31.target
                    mid = (p31.disp_high + p31.disp_low) / 2.0
                    signals.append(_mk_signal(signal_id, ts, i, sig_type, px, row, atr, p31, mid, idx))

        if p31.state == "IDLE":
            p31.dedupe.reset_day_if_needed(ts)
            if disp_dir == "Long" and p31.dedupe.pass_dedupe(i, 1):
                p31.direction = 1
                p31.bos_level = float(row.high)
                p31.tol = BOS_RETEST_TOL_ATR * atr
                p31.disp_bar = i
                p31.disp_ts = ts
                p31.disp_high = float(row.high)
                p31.disp_low = float(row.low)
                p31.deadline = i + P31_BOS_RETEST_WIN
                p31.state = "WAIT"
                p31.dedupe.register(i, 1, ts)
            elif disp_dir == "Short" and p31.dedupe.pass_dedupe(i, -1):
                p31.direction = -1
                p31.bos_level = float(row.low)
                p31.tol = BOS_RETEST_TOL_ATR * atr
                p31.disp_bar = i
                p31.disp_ts = ts
                p31.disp_high = float(row.high)
                p31.disp_low = float(row.low)
                p31.deadline = i + P31_BOS_RETEST_WIN
                p31.state = "WAIT"
                p31.dedupe.register(i, -1, ts)

        # ── New reversal candidate on every displacement (no dedupe at displacement) ──
        if disp_dir is not None:
            disp_count += 1
            cand_count += 1
            rev = _rev_direction(disp_dir)
            cand = ReversalCandidate(
                candidate_id=cand_count,
                displacement_id=disp_count,
                disp_bar=i,
                disp_ts=ts,
                disp_dir=disp_dir,
                rev_dir=rev,
                disp_high=float(row.high),
                disp_low=float(row.low),
                midpoint=(float(row.high) + float(row.low)) / 2.0,
                expiry_bar=i + P33_FAILURE_WIN,
                event_id=f"A_MID_4_{ts}_{rev}",
            )
            active.append(cand)
            _log_candidate(candidate_rows, ts, cand)

        # ── Update active reversal candidates ──
        reclaiming: List[ReversalCandidate] = []
        fired: List[ReversalCandidate] = []
        still_active: List[ReversalCandidate] = []
        concurrency_samples.append(len(active))

        for cand in active:
            if cand.state == "WAIT_FOR_RECLAIM":
                if i > cand.expiry_bar:
                    cand.state = "EXPIRED"
                    _log_candidate(candidate_rows, ts, cand)
                    continue
                if i > cand.disp_bar and _midpoint_reclaimed(
                    cand.disp_dir, cand.midpoint, float(row.close)
                ):
                    reclaiming.append(cand)
                else:
                    still_active.append(cand)

            elif cand.state == "WAIT_FOR_RETEST":
                if i > cand.retest_deadline:
                    cand.state = "EXPIRED"
                    _log_candidate(candidate_rows, ts, cand)
                    continue
                if i > cand.reclaim_bar:
                    dcode = 1 if cand.rev_dir == "Long" else -1
                    filled, px = _try_bos_retest_fill(dcode, cand.reclaim_level, cand.tol, row)
                    if filled:
                        risk = P33_STOP_ATR * atr
                        cand.entry_price = px
                        cand.stop = px - risk if dcode == 1 else px + risk
                        cand.target = px + P33_TARGET_R * risk if dcode == 1 else px - P33_TARGET_R * risk
                        cand.fill_bar = i
                        cand.fill_ts = ts
                        cand.state = "FIRED"
                        _log_candidate(candidate_rows, ts, cand)
                        fired.append(cand)
                        continue
                still_active.append(cand)

        reclaiming.sort(key=lambda c: (c.disp_bar, c.candidate_id))
        for cand in reclaiming:
            cand.reclaim_bar = i
            cand.reclaim_ts = ts
            cand.reclaim_level = cand.midpoint
            cand.tol = BOS_RETEST_TOL_ATR * atr
            cand.retest_deadline = i + P33_RETEST_WIN
            if rev_dedupe.try_keep(
                bar_i=i, direction=cand.rev_dir, event_id=cand.event_id, ts=ts
            ):
                cand.dedupe_passed = True
                cand.state = "WAIT_FOR_RETEST"
                still_active.append(cand)
            else:
                cand.state = "DEDUPED"
            _log_candidate(candidate_rows, ts, cand)

        active = still_active
        # Emit fills (dedupe already passed at reclaim)
        fired = [c for c in fired if c.dedupe_passed]
        fired.sort(key=lambda c: (c.disp_bar, c.candidate_id))
        # Same-bar display resolution: at most one RL and one RS per bar (earliest displacement wins)
        seen_dir: set = set()
        for cand in fired:
            sig_type = "RL" if cand.rev_dir == "Long" else "RS"
            if sig_type in seen_dir:
                continue
            seen_dir.add(sig_type)
            signal_id += 1
            rl_fire = cand.rev_dir == "Long"
            rs_fire = cand.rev_dir == "Short"
            fire_type = sig_type
            fire_entry = cand.entry_price
            fire_stop = cand.stop
            fire_target = cand.target
            expiry_i = min(i + P33_MAX_HOLD_BARS, n - 1)
            signals.append(
                {
                    "signal_id": signal_id,
                    "candidate_id": cand.candidate_id,
                    "candidate_ids": str(cand.candidate_id),
                    "marker_bar_timestamp": ts,
                    "timestamp_ct": ts,
                    "bar_index": i,
                    "signal_type": sig_type,
                    "direction": cand.rev_dir,
                    "entry_price": cand.entry_price,
                    "open": float(row.open),
                    "high": float(row.high),
                    "low": float(row.low),
                    "close": float(row.close),
                    "atr": atr,
                    "source_displacement_time": cand.disp_ts,
                    "source_displacement_high": cand.disp_high,
                    "source_displacement_low": cand.disp_low,
                    "source_displacement_midpoint": cand.midpoint,
                    "bos_or_reclaim_time": cand.reclaim_ts,
                    "reclaim_level": cand.reclaim_level,
                    "retest_time": ts,
                    "stop": cand.stop,
                    "target": cand.target,
                    "expiry_time": idx[expiry_i],
                    "architecture": "DISPLACEMENT_FAILURE_REVERSAL",
                    "event_id": cand.event_id,
                }
            )

        if rth:
            state_rows.append(
                {
                    "timestamp": ts,
                    "bar_index": i,
                    "active_candidates": len(active),
                    "continuation_state": p31.state,
                    "L_fire": l_fire,
                    "S_fire": s_fire,
                    "RL_fire": rl_fire,
                    "RS_fire": rs_fire,
                    "entry_price": fire_entry if fire_type else np.nan,
                    "stop": fire_stop if fire_type else np.nan,
                    "target": fire_target if fire_type else np.nan,
                }
            )

    sig_df = pd.DataFrame(signals)
    cand_df = pd.DataFrame(candidate_rows)
    state_df = pd.DataFrame(state_rows)
    if concurrency_samples:
        sig_df.attrs["concurrency_samples"] = concurrency_samples
    return sig_df, cand_df, state_df


def _log_candidate(rows: List[dict], ts: pd.Timestamp, cand: ReversalCandidate) -> None:
    rows.append(
        {
            "timestamp": ts,
            "candidate_id": cand.candidate_id,
            "displacement_id": cand.displacement_id,
            "state": cand.state,
            "disp_bar": cand.disp_bar,
            "reclaim_bar": cand.reclaim_bar,
            "fill_bar": cand.fill_bar,
            "dedupe_passed": cand.dedupe_passed,
            "event_id": cand.event_id,
        }
    )


def _mk_signal(signal_id, ts, i, sig_type, px, row, atr, p31, mid, idx) -> dict:
    direction = "Long" if sig_type == "L" else "Short"
    risk = P31_STOP_ATR * atr
    stop = px - risk if sig_type == "L" else px + risk
    target = px + P31_TARGET_R * risk if sig_type == "L" else px - P31_TARGET_R * risk
    expiry_i = min(i + P31_MAX_HOLD_BARS, len(idx) - 1)
    return {
        "signal_id": signal_id,
        "candidate_id": np.nan,
        "candidate_ids": "",
        "marker_bar_timestamp": ts,
        "timestamp_ct": ts,
        "bar_index": i,
        "signal_type": sig_type,
        "direction": direction,
        "entry_price": px,
        "open": float(row.open),
        "high": float(row.high),
        "low": float(row.low),
        "close": float(row.close),
        "atr": atr,
        "source_displacement_time": p31.disp_ts,
        "source_displacement_high": p31.disp_high,
        "source_displacement_low": p31.disp_low,
        "source_displacement_midpoint": mid,
        "bos_or_reclaim_time": p31.disp_ts,
        "bos_level": p31.bos_level,
        "retest_time": ts,
        "stop": stop,
        "target": target,
        "expiry_time": idx[expiry_i],
        "architecture": "MOMENTUM_DISPLACEMENT",
        "event_id": f"MOMENTUM_DISPLACEMENT_{p31.disp_ts}_{direction}",
    }
