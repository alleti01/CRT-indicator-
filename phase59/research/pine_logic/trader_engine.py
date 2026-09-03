"""Sequential trader engine — one closed bar at a time."""
from __future__ import annotations

import json
import numpy as np
import pandas as pd

from phase58.research.precompute import MarketArrays
from phase58.research.context import compute_context
from phase58.research.location import compute_location
from phase58.research.reaction import compute_all_reactions
from phase58.research.trader_state import (
    ActiveTrade, Decision, State, TraderSnapshot, TraderState,
)
from phase58.research.instrument import InstrumentSpec, NQ


class TraderEngine:
    """Chronological finite-state trader. Process bars sequentially."""

    def __init__(self, m: MarketArrays, cfg: dict, instrument: InstrumentSpec = NQ):
        self.m = m
        self.cfg = cfg
        self.inst = instrument
        self.st = TraderState()
        self.warmup = max(100, cfg.get("swing_period", 5) * 3)

    def on_bar_close(self, i: int) -> TraderSnapshot:
        m = self.m; st = self.st; cfg = self.cfg
        if i < self.warmup or i >= m.n - 61:
            snap = TraderSnapshot(bar_i=i, state=st.state, decision=Decision.WATCH,
                direction="", context_dir="NEUTRAL", context_confidence=0,
                location_score=0, reaction_score=0, total_score=0,
                armed_i=-1, armed_price=0, pb_extreme_price=0,
                entry_deterioration_atr=0, reasons=[])
            st.decisions.append(self._snap_to_dict(snap))
            return snap

        a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0

        # ── Manage active trade ───────────────────────────────────────
        if st.trade is not None:
            exit_result = self._manage_trade(i)
            if exit_result is not None:
                return exit_result
            snap = TraderSnapshot(bar_i=i, state=st.state, decision=Decision.HOLD,
                direction=st.direction, context_dir="", context_confidence=0,
                location_score=0, reaction_score=0, total_score=0,
                armed_i=st.armed_i, armed_price=st.armed_price,
                pb_extreme_price=st.pb_extreme, entry_deterioration_atr=0,
                reasons=["HOLDING"], trade=st.trade)
            st.decisions.append(self._snap_to_dict(snap))
            return snap

        # ── Cooldown ──────────────────────────────────────────────────
        if st.state == State.COOLDOWN:
            st.cooldown_remaining -= 1
            if st.cooldown_remaining <= 0:
                st.reset_to_watch()
            snap = TraderSnapshot(bar_i=i, state=st.state, decision=Decision.WATCH,
                direction="", context_dir="NEUTRAL", context_confidence=0,
                location_score=0, reaction_score=0, total_score=0,
                armed_i=-1, armed_price=0, pb_extreme_price=0,
                entry_deterioration_atr=0, reasons=["COOLDOWN"])
            st.decisions.append(self._snap_to_dict(snap))
            return snap

        # ── Compute context ───────────────────────────────────────────
        ctx = compute_context(m, i)
        ctx_dir = ctx["direction"]
        ctx_conf = ctx["confidence"]
        ctx_reasons = ctx["reasons"]

        # ── WATCH → ARMED transition ──────────────────────────────────
        if st.state == State.WATCH:
            trade_dir = None
            if ctx_dir == "BULLISH":
                trade_dir = "LONG"
            elif ctx_dir == "BEARISH":
                trade_dir = "SHORT"
            if trade_dir:
                loc = compute_location(m, i, trade_dir)
                ctx_score = min(2, ctx["bull_score"] if trade_dir == "LONG" else ctx["bear_score"])
                loc_score = loc["score"]
                total = ctx_score + loc_score
                if total >= cfg.get("armed_min_score", 2):
                    st.state = State.ARMED_LONG if trade_dir == "LONG" else State.ARMED_SHORT
                    st.direction = trade_dir
                    st.armed_i = i
                    st.armed_price = m.cl[i]
                    st.armed_bars = 0
                    st.pb_extreme = m.cl[i]
                    reasons = ctx_reasons + loc["reasons"]
                    snap = TraderSnapshot(bar_i=i, state=st.state, decision=Decision.ARMED,
                        direction=trade_dir, context_dir=ctx_dir, context_confidence=ctx_conf,
                        location_score=loc_score, reaction_score=0, total_score=total,
                        armed_i=i, armed_price=m.cl[i], pb_extreme_price=m.cl[i],
                        entry_deterioration_atr=0, reasons=reasons)
                    st.decisions.append(self._snap_to_dict(snap))
                    return snap
            snap = TraderSnapshot(bar_i=i, state=State.WATCH, decision=Decision.WATCH,
                direction="", context_dir=ctx_dir, context_confidence=ctx_conf,
                location_score=0, reaction_score=0, total_score=0,
                armed_i=-1, armed_price=0, pb_extreme_price=0,
                entry_deterioration_atr=0, reasons=[])
            st.decisions.append(self._snap_to_dict(snap))
            return snap

        # ── ARMED / REACTION states ───────────────────────────────────
        st.armed_bars += 1
        # Update running pullback extreme
        if st.direction == "LONG":
            st.pb_extreme = min(st.pb_extreme, m.lo[i])
        else:
            st.pb_extreme = max(st.pb_extreme, m.hi[i])

        # Timeout
        if st.armed_bars > cfg.get("armed_timeout_bars", 15):
            reasons_out = ["ARMED_TIMEOUT"]
            st.reset_to_watch()
            snap = TraderSnapshot(bar_i=i, state=State.WATCH, decision=Decision.INVALIDATED,
                direction="", context_dir=ctx_dir, context_confidence=ctx_conf,
                location_score=0, reaction_score=0, total_score=0,
                armed_i=-1, armed_price=0, pb_extreme_price=0,
                entry_deterioration_atr=0, reasons=reasons_out)
            st.decisions.append(self._snap_to_dict(snap))
            return snap

        # Context contradiction → invalidate
        if (st.direction == "LONG" and ctx_dir == "BEARISH") or \
           (st.direction == "SHORT" and ctx_dir == "BULLISH"):
            reasons_out = ["CTX_CONTRA"]
            st.reset_to_watch()
            snap = TraderSnapshot(bar_i=i, state=State.WATCH, decision=Decision.INVALIDATED,
                direction="", context_dir=ctx_dir, context_confidence=ctx_conf,
                location_score=0, reaction_score=0, total_score=0,
                armed_i=-1, armed_price=0, pb_extreme_price=0,
                entry_deterioration_atr=0, reasons=reasons_out)
            st.decisions.append(self._snap_to_dict(snap))
            return snap

        # Compute reaction evidence
        react = compute_all_reactions(m, i, st.direction, cfg)
        loc = compute_location(m, i, st.direction)
        ctx_score = min(2, ctx["bull_score"] if st.direction == "LONG" else ctx["bear_score"])
        loc_score = loc["score"]

        # Contradiction score
        contra = 0
        contra_reasons = []
        if st.direction == "LONG" and ctx_dir == "NEUTRAL" and ctx["bear_score"] >= 2:
            contra -= 1; contra_reasons.append("CONTRA_BEAR")
        elif st.direction == "SHORT" and ctx_dir == "NEUTRAL" and ctx["bull_score"] >= 2:
            contra -= 1; contra_reasons.append("CONTRA_BULL")

        total = ctx_score + loc_score + react["score"] + contra
        all_reasons = ctx_reasons + loc["reasons"] + react["reasons"] + contra_reasons

        # Entry deterioration
        if st.direction == "LONG":
            deterioration = (m.cl[i] - st.armed_price) / a
        else:
            deterioration = (st.armed_price - m.cl[i]) / a

        # Anti-chase check
        max_chase = cfg.get("max_chase_atr", 1.5)
        if deterioration > max_chase and react["score"] >= 1:
            st.reset_to_watch()
            snap = TraderSnapshot(bar_i=i, state=State.WATCH, decision=Decision.MISSED_NO_CHASE,
                direction=st.direction, context_dir=ctx_dir, context_confidence=ctx_conf,
                location_score=loc_score, reaction_score=react["score"], total_score=total,
                armed_i=st.armed_i, armed_price=st.armed_price,
                pb_extreme_price=st.pb_extreme, entry_deterioration_atr=deterioration,
                reasons=all_reasons + ["NO_CHASE"])
            st.decisions.append(self._snap_to_dict(snap))
            return snap

        # TAKE decision
        if total >= cfg.get("take_threshold", 4):
            return self._take_trade(i, ctx_dir, ctx_conf, loc_score, react["score"],
                                     total, deterioration, all_reasons)

        # Still ARMED/waiting
        decision = Decision.WAIT if react["score"] >= 1 else Decision.ARMED
        snap = TraderSnapshot(bar_i=i, state=st.state, decision=decision,
            direction=st.direction, context_dir=ctx_dir, context_confidence=ctx_conf,
            location_score=loc_score, reaction_score=react["score"], total_score=total,
            armed_i=st.armed_i, armed_price=st.armed_price,
            pb_extreme_price=st.pb_extreme, entry_deterioration_atr=deterioration,
            reasons=all_reasons)
        st.decisions.append(self._snap_to_dict(snap))
        return snap

    def _take_trade(self, i, ctx_dir, ctx_conf, loc_score, react_score, total, deterioration, reasons):
        m = self.m; st = self.st; cfg = self.cfg
        a = m.atr[i] if np.isfinite(m.atr[i]) and m.atr[i] > 0 else 1.0
        entry_i = i + 1  # next bar open
        if entry_i >= m.n - 61:
            st.reset_to_watch()
            return self._watch_snap(i, ctx_dir, ctx_conf, ["ENTRY_OOB"])
        ep = m.cl[entry_i]  # use close of next bar as proxy for open
        risk = cfg.get("stop_atr", 0.75) * a
        d = 1 if st.direction == "LONG" else -1
        stop = ep - risk if d == 1 else ep + risk
        target = ep + cfg.get("target_r", 2.5) * risk if d == 1 else ep - cfg.get("target_r", 2.5) * risk
        deadline = min(m.n - 1, entry_i + cfg.get("max_hold_min", 60))

        st.signal_counter += 1
        st.trade = ActiveTrade(
            signal_i=i, entry_i=entry_i, entry_price=ep,
            direction=st.direction, atr=a, stop=stop, target=target,
            exit_deadline_i=deadline)
        st.state = State.IN_LONG if st.direction == "LONG" else State.IN_SHORT

        decision = Decision.TAKE_LONG if st.direction == "LONG" else Decision.TAKE_SHORT
        snap = TraderSnapshot(bar_i=i, state=st.state, decision=decision,
            direction=st.direction, context_dir=ctx_dir, context_confidence=ctx_conf,
            location_score=loc_score, reaction_score=react_score, total_score=total,
            armed_i=st.armed_i, armed_price=st.armed_price,
            pb_extreme_price=st.pb_extreme, entry_deterioration_atr=deterioration,
            reasons=reasons + ["TAKE"], trade=st.trade)
        st.decisions.append(self._snap_to_dict(snap))
        return snap

    def _manage_trade(self, i) -> TraderSnapshot | None:
        m = self.m; st = self.st; t = st.trade
        if t is None:
            return None
        if i <= t.entry_i:
            return None
        d = 1 if t.direction == "LONG" else -1
        risk = abs(t.entry_price - t.stop)
        if risk <= 0:
            return self._close_trade(i, m.cl[i], "ZERO_RISK", 0)
        h, l, c = m.hi[i], m.lo[i], m.cl[i]
        if d == 1:
            t.mfe = max(t.mfe, (h - t.entry_price) / risk)
            t.mae = max(t.mae, (t.entry_price - l) / risk)
            if l <= t.stop:
                return self._close_trade(i, t.stop, "STOP", -1.0)
            if h >= t.target:
                return self._close_trade(i, t.target, "TARGET", self.cfg.get("target_r", 2.5))
        else:
            t.mfe = max(t.mfe, (t.entry_price - l) / risk)
            t.mae = max(t.mae, (h - t.entry_price) / risk)
            if h >= t.stop:
                return self._close_trade(i, t.stop, "STOP", -1.0)
            if l <= t.target:
                return self._close_trade(i, t.target, "TARGET", self.cfg.get("target_r", 2.5))
        if i >= t.exit_deadline_i:
            realized = (c - t.entry_price) / risk * d
            return self._close_trade(i, c, "TIME", realized)
        return None

    def _close_trade(self, i, exit_price, reason, gross_r):
        st = self.st; t = st.trade
        cr = self.inst.cost_r(t.entry_price, t.stop)
        st.trade_counter += 1
        trade_rec = {
            "trade_id": f"T58-{st.trade_counter:06d}",
            "signal_i": t.signal_i, "entry_i": t.entry_i,
            "entry_price": t.entry_price, "exit_i": i,
            "exit_price": exit_price, "exit_reason": reason,
            "direction": t.direction, "atr": t.atr,
            "stop": t.stop, "target": t.target,
            "gross_R": gross_r, "cost_R": cr,
            "net_R": gross_r - cr, "MFE_R": t.mfe, "MAE_R": t.mae,
            "duration": i - t.entry_i,
        }
        st.trades.append(trade_rec)
        st.trade = None
        st.state = State.COOLDOWN
        st.cooldown_remaining = self.cfg.get("cooldown_bars", 3)
        st.direction = ""
        decision = {"STOP": Decision.EXIT_STOP, "TARGET": Decision.EXIT_TARGET, "TIME": Decision.EXIT_TIME}.get(reason, Decision.EXIT_STOP)
        snap = TraderSnapshot(bar_i=i, state=State.COOLDOWN, decision=decision,
            direction=trade_rec["direction"], context_dir="", context_confidence=0,
            location_score=0, reaction_score=0, total_score=0,
            armed_i=-1, armed_price=0, pb_extreme_price=0,
            entry_deterioration_atr=0, reasons=[f"EXIT_{reason}"])
        st.decisions.append(self._snap_to_dict(snap))
        return snap

    def _watch_snap(self, i, ctx_dir, ctx_conf, reasons):
        self.st.reset_to_watch()
        snap = TraderSnapshot(bar_i=i, state=State.WATCH, decision=Decision.WATCH,
            direction="", context_dir=ctx_dir, context_confidence=ctx_conf,
            location_score=0, reaction_score=0, total_score=0,
            armed_i=-1, armed_price=0, pb_extreme_price=0,
            entry_deterioration_atr=0, reasons=reasons)
        self.st.decisions.append(self._snap_to_dict(snap))
        return snap

    def _snap_to_dict(self, snap: TraderSnapshot) -> dict:
        return {
            "bar_i": snap.bar_i, "state": snap.state.value,
            "decision": snap.decision.value, "direction": snap.direction,
            "context_dir": snap.context_dir, "context_confidence": snap.context_confidence,
            "location_score": snap.location_score, "reaction_score": snap.reaction_score,
            "total_score": snap.total_score,
            "armed_i": snap.armed_i, "armed_price": snap.armed_price,
            "pb_extreme": snap.pb_extreme_price,
            "entry_deterioration_atr": snap.entry_deterioration_atr,
            "reasons": "|".join(snap.reasons),
        }

    def run(self, start_i: int = 0, end_i: int | None = None) -> None:
        s = max(self.warmup, start_i)
        e = end_i if end_i is not None else self.m.n - 61
        for i in range(s, e):
            self.on_bar_close(i)

    def results(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        decisions = pd.DataFrame(self.st.decisions) if self.st.decisions else pd.DataFrame()
        trades = pd.DataFrame(self.st.trades) if self.st.trades else pd.DataFrame()
        return decisions, trades
