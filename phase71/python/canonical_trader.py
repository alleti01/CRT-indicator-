"""Phase71 — unified deterministic trader state machine."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from phase58.research.instrument import NQ

FROZEN_SPEC = {
    "signal_hash": "0da41f282174679f",
    "entry": "signal bar T close → entry next 1M open T+1",
    "initial_stop_atr": 1.0,
    "target_r": 2.5,
    "max_hold_minutes": 60,
    "collision": "STOP_FIRST",
    "t5_minutes": 15,
    "t5_mfe_threshold_r": 1.0,
    "t5_mfe_pass": "MFE_R >= 1.0 holds; MFE_R < 1.0 exits",
    "t5_once": True,
    "position_limit": 1,
    "opposite_signal": "OPPOSITE_SIGNAL_IGNORED_IN_POSITION",
}


def trader_hash() -> str:
    return hashlib.sha256(json.dumps(FROZEN_SPEC, sort_keys=True).encode()).hexdigest()[:16]


class State(str, Enum):
    FLAT = "FLAT"
    LONG_ACTIVE = "LONG_ACTIVE"
    SHORT_ACTIVE = "SHORT_ACTIVE"


class Action(str, Enum):
    WATCH = "WATCH"
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    HOLD_LONG = "HOLD_LONG"
    HOLD_SHORT = "HOLD_SHORT"
    EXIT_STOP = "EXIT_STOP"
    EXIT_TARGET = "EXIT_TARGET"
    EXIT_TIME_PROGRESS = "EXIT_TIME_PROGRESS"
    EXIT_MAX_HOLD = "EXIT_MAX_HOLD"


REASON = {
    "M0_STOP": "M0_STOP",
    "M0_TARGET": "M0_TARGET",
    "T5_NO_PROGRESS": "T5_NO_PROGRESS",
    "MAX_HOLD_60M": "MAX_HOLD_60M",
    "NO_ACTION": "NO_ACTION",
    "SIGNAL_LONG": "SIGNAL_LONG",
    "SIGNAL_SHORT": "SIGNAL_SHORT",
}


@dataclass
class ActiveTrade:
    trade_id: str
    direction: str
    signal_i: int
    entry_i: int
    entry_price: float
    initial_atr: float
    risk: float
    stop_price: float
    target_price: float
    entry_ts: object = None
    signal_ts: object = None
    running_mfe_r: float = 0.0
    t5_checked: bool = False
    t5_time: Optional[int] = None
    mfe_at_t5_r: Optional[float] = None
    t5_result: Optional[str] = None


@dataclass
class TraderConfig:
    enable_t5: bool = True
    t5_minutes: int = 15
    t5_mfe_r: float = 1.0
    max_hold: int = 60
    stop_atr: float = 1.0
    target_r: float = 2.5
    one_position: bool = False


def _risk_stop(ep: float, direction: str, atr: float, stop_atr: float) -> tuple[float, float]:
    risk = stop_atr * atr
    if risk <= 0:
        risk = max(0.25 * atr, 1e-9)
    if direction == "LONG":
        return ep - risk, risk
    return ep + risk, risk


def manage_trade_bars(
    trade: ActiveTrade,
    hi, lo, cl, op,
    n: int,
    cfg: TraderConfig,
    timestamps=None,
) -> tuple[dict, list[dict]]:
    """Bar-by-bar management from entry bar. Event order per Phase71 spec."""
    d = 1 if trade.direction == "LONG" else -1
    ep, risk = trade.entry_price, trade.risk
    stop, target = trade.stop_price, trade.target_price
    end_i = min(trade.entry_i + cfg.max_hold, n - 1)
    decisions: list[dict] = []
    exit_rec: Optional[dict] = None

    state = State.LONG_ACTIVE if trade.direction == "LONG" else State.SHORT_ACTIVE

    for k in range(trade.entry_i + 1, end_i + 1):
        h, l, c = float(hi[k]), float(lo[k]), float(cl[k])
        minutes = k - trade.entry_i
        ts = timestamps[k] if timestamps is not None and k < len(timestamps) else k

        hit_stop = l <= stop if d == 1 else h >= stop
        hit_tgt = h >= target if d == 1 else l <= target
        action = Action.HOLD_LONG if d == 1 else Action.HOLD_SHORT
        reason = REASON["NO_ACTION"]
        state_after = state
        exited = False

        # 2-4: stop / target / STOP_FIRST
        if hit_stop and hit_tgt:
            gross_r = -1.0
            exit_px = stop
            action = Action.EXIT_STOP
            reason = REASON["M0_STOP"]
            exited = True
        elif hit_stop:
            gross_r = -1.0
            exit_px = stop
            action = Action.EXIT_STOP
            reason = REASON["M0_STOP"]
            exited = True
        elif hit_tgt:
            gross_r = cfg.target_r
            exit_px = target
            action = Action.EXIT_TARGET
            reason = REASON["M0_TARGET"]
            exited = True

        if not exited:
            # 5: update running MFE (bars after entry only)
            bar_fav = (h - ep) * d / risk
            trade.running_mfe_r = max(trade.running_mfe_r, bar_fav)

            # 6: T5 one-time checkpoint
            if cfg.enable_t5 and not trade.t5_checked and minutes >= cfg.t5_minutes:
                trade.t5_checked = True
                trade.t5_time = k
                trade.mfe_at_t5_r = trade.running_mfe_r
                if trade.running_mfe_r < cfg.t5_mfe_r:
                    trade.t5_result = "FAIL"
                    gross_r = (c - ep) * d / risk
                    exit_px = c
                    action = Action.EXIT_TIME_PROGRESS
                    reason = REASON["T5_NO_PROGRESS"]
                    exited = True
                else:
                    trade.t5_result = "PASS"

            # 7: hard max hold at end of hold window
            if not exited and k == end_i:
                gross_r = (c - ep) * d / risk
                exit_px = c
                action = Action.EXIT_MAX_HOLD
                reason = REASON["MAX_HOLD_60M"]
                exited = True

        dec = {
            "timestamp": ts,
            "bar_index": k,
            "state_before": state.value,
            "signal": trade.trade_id,
            "signal_direction": trade.direction,
            "entry_pending": False,
            "entry_price": ep,
            "direction": trade.direction,
            "initial_atr": trade.initial_atr,
            "stop_price": stop,
            "target_price": target,
            "minutes_in_trade": minutes,
            "running_mfe_r": trade.running_mfe_r,
            "t5_checked": trade.t5_checked,
            "action": action.value,
            "reason_code": reason,
            "state_after": State.FLAT.value if exited else state.value,
            "known_at": k,
        }
        decisions.append(dec)

        if exited:
            cost = NQ.cost_r(ep, risk)
            exit_rec = {
                "trade_id": trade.trade_id,
                "signal_time": trade.signal_ts,
                "entry_time": trade.entry_ts,
                "entry_price": ep,
                "direction": trade.direction,
                "initial_atr": trade.initial_atr,
                "stop_price": stop,
                "target_price": target,
                "t5_time": trade.t5_time,
                "mfe_at_t5_r": trade.mfe_at_t5_r,
                "t5_result": trade.t5_result,
                "exit_time": ts,
                "exit_bar": k,
                "exit_price": exit_px,
                "exit_reason": reason,
                "gross_r": gross_r,
                "net_r": gross_r - cost,
                "hold_minutes": minutes,
                "entry_i": trade.entry_i,
            }
            break

    if exit_rec is None:
        exit_rec = {"trade_id": trade.trade_id, "exit_reason": "NO_EXIT", "gross_r": 0.0, "net_r": 0.0}

    return exit_rec, decisions


def run_independent(
    execs: pd.DataFrame,
    m,
    cfg: TraderConfig,
    timestamps=None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    """One trade per signal — matches Phase70 historical batch semantics."""
    trades, all_decisions = [], []
    ts = timestamps if timestamps is not None else getattr(m, "ts", None)

    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65:
            continue
        atr = float(ex["atr_entry"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        stop, risk = _risk_stop(float(ex["entry_price"]), ex["direction"], atr, cfg.stop_atr)
        tgt = float(ex["entry_price"]) + (1 if ex["direction"] == "LONG" else -1) * cfg.target_r * risk
        trade = ActiveTrade(
            trade_id=ex["trade_id"],
            direction=ex["direction"],
            signal_i=int(ex["signal_i"]),
            entry_i=ei,
            entry_price=float(ex["entry_price"]),
            initial_atr=atr,
            risk=risk,
            stop_price=stop,
            target_price=tgt,
            entry_ts=ex.get("entry_ts"),
            signal_ts=ex.get("signal_ts"),
        )
        rec, decs = manage_trade_bars(trade, m.hi, m.lo, m.cl, m.op, m.n, cfg, ts)
        trades.append(rec)
        all_decisions.extend(decs)
    return pd.DataFrame(trades), pd.DataFrame(all_decisions), trades


def run_one_position(
    execs: pd.DataFrame,
    m,
    cfg: TraderConfig,
    timestamps=None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Live bot semantics: max 1 position, skip signals while active."""
    execs = execs.sort_values("entry_ts").reset_index(drop=True)
    trades, all_decisions = [], []
    skipped = {"N": 0, "LONG": 0, "SHORT": 0, "same_dir": 0, "opposite_dir": 0}
    active_until = -1
    ts = timestamps if timestamps is not None else getattr(m, "ts", None)

    for _, ex in execs.iterrows():
        ei = int(ex["entry_i"])
        if ei >= m.n - 65 or ei <= active_until:
            skipped["N"] += 1
            skipped[ex["direction"]] = skipped.get(ex["direction"], 0) + 1
            continue
        atr = float(ex["atr_entry"])
        if not np.isfinite(atr) or atr <= 0:
            continue
        stop, risk = _risk_stop(float(ex["entry_price"]), ex["direction"], atr, cfg.stop_atr)
        tgt = float(ex["entry_price"]) + (1 if ex["direction"] == "LONG" else -1) * cfg.target_r * risk
        trade = ActiveTrade(
            trade_id=ex["trade_id"], direction=ex["direction"],
            signal_i=int(ex["signal_i"]), entry_i=ei,
            entry_price=float(ex["entry_price"]), initial_atr=atr,
            risk=risk, stop_price=stop, target_price=tgt,
            entry_ts=ex.get("entry_ts"),
        )
        rec, decs = manage_trade_bars(trade, m.hi, m.lo, m.cl, m.op, m.n, cfg, ts)
        trades.append(rec)
        all_decisions.extend(decs)
        active_until = int(rec.get("exit_bar", ei))
    return pd.DataFrame(trades), pd.DataFrame(all_decisions), skipped


def classify_attribution(m0_gross: float, t5_gross: float) -> str:
    if abs(m0_gross - t5_gross) < 1e-9:
        return "NO_CHANGE"
    if m0_gross <= -0.99 and t5_gross > -0.99:
        return "SAVED_STOP"
    if m0_gross >= 2.5 - 1e-9 and t5_gross < 2.5 - 0.01:
        return "KILLED_WINNER"
    if m0_gross < 0 and t5_gross > m0_gross + 0.05:
        return "CUT_SMALL_LOSS"
    if m0_gross > 0 and t5_gross < m0_gross - 0.05:
        return "CUT_SMALL_WIN"
    if abs(m0_gross) < 0.15 and abs(t5_gross) < 0.15:
        return "CUT_BREAKEVEN"
    return "NO_CHANGE"


def persist_state(trade: ActiveTrade) -> dict:
    return {
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "entry_i": trade.entry_i,
        "initial_atr": trade.initial_atr,
        "stop_price": trade.stop_price,
        "target_price": trade.target_price,
        "running_mfe_r": trade.running_mfe_r,
        "t5_checked": trade.t5_checked,
        "risk": trade.risk,
    }


def restore_trade(trade_id: str, state: dict, signal_i: int, entry_ts=None) -> ActiveTrade:
    return ActiveTrade(
        trade_id=trade_id,
        direction=state["direction"],
        signal_i=signal_i,
        entry_i=state["entry_i"],
        entry_price=state["entry_price"],
        initial_atr=state["initial_atr"],
        risk=state["risk"],
        stop_price=state["stop_price"],
        target_price=state["target_price"],
        entry_ts=entry_ts,
        running_mfe_r=state["running_mfe_r"],
        t5_checked=state["t5_checked"],
    )
