"""5M primary decision engine — chronological state machine."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np
import pandas as pd

from phase58b.research.context_15m import (
    compute_15m_context,
    score_15m_for_direction,
    strong_contradiction,
)
from phase58b.research.context_5m import compute_5m_structure
from phase58b.research.location_5m import compute_5m_location
from phase58b.research.precompute import MTFArrays
from phase58b.research.reaction_5m import compute_5m_reactions


class FiveMState(str, Enum):
    WATCH = "WATCH"
    CONTEXT_READY = "CONTEXT_READY"
    ARMED_LONG = "ARMED_LONG"
    ARMED_SHORT = "ARMED_SHORT"
    REACTION_LONG = "REACTION_LONG"
    REACTION_SHORT = "REACTION_SHORT"
    ACTIVE_SETUP = "ACTIVE_SETUP"
    COOLDOWN = "COOLDOWN"


class FiveMDecision(str, Enum):
    WATCH = "WATCH"
    ARM_LONG = "ARM_LONG"
    ARM_SHORT = "ARM_SHORT"
    REACTION = "REACTION"
    TAKE_LONG = "TAKE_LONG"
    TAKE_SHORT = "TAKE_SHORT"
    PASS = "PASS"
    INVALIDATED = "INVALIDATED"
    RESET = "RESET"


@dataclass
class SetupRecord:
    setup_id: str
    direction: str
    armed_j: int
    armed_price: float
    take_j: int = -1
    take_price: float = 0.0
    tag: str = "CONTINUATION"
    state: str = "ARMED"


@dataclass
class FiveMTraderState:
    state: FiveMState = FiveMState.WATCH
    direction: str = ""
    armed_j: int = -1
    armed_price: float = 0.0
    armed_bars: int = 0
    pb_extreme: float = 0.0
    cooldown_remaining: int = 0
    setup_counter: int = 0
    active_setup_id: str = ""
    last_impulse_dir: str = ""
    decisions: list[dict] = field(default_factory=list)
    setups: list[dict] = field(default_factory=list)
    takes: list[dict] = field(default_factory=list)


class FiveMTraderEngine:
    """Process 5M bars chronologically. Outputs ARM/TAKE/PASS decisions."""

    def __init__(self, m: MTFArrays, cfg: dict, use_15m: bool = True, hard_filter: bool = False):
        self.m = m
        self.cfg = cfg
        self.use_15m = use_15m
        self.hard_filter = hard_filter
        self.st = FiveMTraderState()
        self.warmup = max(30, cfg.get("swing_period_5m", 5) * 3)

    def run(self, end_j: int | None = None) -> None:
        e = end_j if end_j is not None else self.m.m5_n - 13
        for j in range(self.warmup, e):
            self.on_bar_close(j)

    def on_bar_close(self, j: int) -> dict:
        m, st, cfg = self.m, self.st, self.cfg
        a = _atr(m.m5_atr[j], m.m5_atr, j)

        ctx15 = compute_15m_context(m, j, cfg) if self.use_15m else _flat_15m()
        struct = compute_5m_structure(m, j, cfg)

        if st.state == FiveMState.COOLDOWN:
            st.cooldown_remaining -= 1
            if st.cooldown_remaining <= 0:
                self._reset_watch()
            return self._log(j, FiveMState.WATCH, FiveMDecision.WATCH, "", ctx15, struct, 0, 0, 0, 0, [])

        if st.state in (FiveMState.ARMED_LONG, FiveMState.ARMED_SHORT, FiveMState.REACTION_LONG, FiveMState.REACTION_SHORT):
            return self._process_armed(j, ctx15, struct, a)

        # WATCH → ARM
        trade_dir = None
        if struct["direction"] == "BULLISH":
            trade_dir = "LONG"
        elif struct["direction"] == "BEARISH":
            trade_dir = "SHORT"

        if trade_dir and self._structural_reset_allows(j, trade_dir):
            loc = compute_5m_location(m, j, trade_dir, cfg)
            struct_score = min(2, struct["score"])
            ctx15_score, _ = score_15m_for_direction(ctx15, trade_dir) if self.use_15m else (0, [])
            arm_gate = struct_score + loc["score"]
            if arm_gate >= cfg.get("armed_min_score", 2):
                st.setup_counter += 1
                st.active_setup_id = f"S58B-{st.setup_counter:06d}"
                st.direction = trade_dir
                st.armed_j = j
                st.armed_price = m.m5_cl[j]
                st.armed_bars = 0
                st.pb_extreme = m.m5_cl[j]
                st.state = FiveMState.ARMED_LONG if trade_dir == "LONG" else FiveMState.ARMED_SHORT
                tag = self._setup_tag(ctx15, trade_dir)
                st.setups.append({
                    "setup_id": st.active_setup_id,
                    "direction": trade_dir,
                    "armed_j": j,
                    "armed_price": m.m5_cl[j],
                    "armed_ts": str(m.m5_idx[j]),
                    "tag": tag,
                    "15m_state": ctx15["state"],
                    "15m_strength": ctx15["strength"],
                })
                dec = FiveMDecision.ARM_LONG if trade_dir == "LONG" else FiveMDecision.ARM_SHORT
                reasons = struct["reasons"] + loc["reasons"] + ctx15.get("reasons", [])
                return self._log(j, st.state, dec, trade_dir, ctx15, struct, ctx15_score, loc["score"], 0, arm_gate, reasons)

        return self._log(j, FiveMState.WATCH, FiveMDecision.WATCH, "", ctx15, struct, 0, 0, 0, 0, [])

    def _process_armed(self, j: int, ctx15: dict, struct: dict, a: float) -> dict:
        st, m, cfg = self.st, self.m, self.cfg
        st.armed_bars += 1
        d = st.direction

        if d == "LONG":
            st.pb_extreme = min(st.pb_extreme, m.m5_lo[j])
        else:
            st.pb_extreme = max(st.pb_extreme, m.m5_hi[j])

        if st.armed_bars > cfg.get("armed_timeout_bars_5m", 15):
            self._invalidate(j, "ARMED_TIMEOUT", ctx15, struct)
            return st.decisions[-1]

        # Hard 5M context contradiction (same as Phase58 — not 15M direction lock)
        if (d == "LONG" and struct["direction"] == "BEARISH") or (d == "SHORT" and struct["direction"] == "BULLISH"):
            self._invalidate(j, "5M_CTX_CONTRA", ctx15, struct)
            return st.decisions[-1]

        loc = compute_5m_location(m, j, d, cfg)
        react = compute_5m_reactions(m, j, d, cfg)
        ctx15_score, r15 = score_15m_for_direction(ctx15, d) if self.use_15m else (0, [])
        struct_score = min(2, struct["bull"] if d == "LONG" else struct["bear"])

        contra = 0
        contra_reasons: list[str] = []
        is_strong, sr = strong_contradiction(ctx15, d, m, j) if self.use_15m else (False, [])
        if is_strong:
            contra -= cfg.get("strong_contra_penalty", 3)
            contra_reasons.extend(sr)

        if self.hard_filter and is_strong:
            self._pass(j, "HARD_CONTRA_FILTER", ctx15, struct, ctx15_score, loc["score"], react["score"], contra, r15 + contra_reasons)
            return st.decisions[-1]

        total = ctx15_score + struct_score + loc["score"] + react["score"] + contra
        all_reasons = r15 + struct["reasons"] + loc["reasons"] + react["reasons"] + contra_reasons

        det = (m.m5_cl[j] - st.armed_price) / a if d == "LONG" else (st.armed_price - m.m5_cl[j]) / a

        if det > cfg.get("max_chase_atr", 1.5) and react["score"] >= 1:
            self._pass(j, "MISSED_NO_CHASE", ctx15, struct, ctx15_score, loc["score"], react["score"], contra, all_reasons + ["NO_CHASE"])
            return st.decisions[-1]

        if react["score"] >= 1 and st.state in (FiveMState.ARMED_LONG, FiveMState.ARMED_SHORT):
            st.state = FiveMState.REACTION_LONG if d == "LONG" else FiveMState.REACTION_SHORT

        if total >= cfg.get("take_threshold", 4):
            dec = FiveMDecision.TAKE_LONG if d == "LONG" else FiveMDecision.TAKE_SHORT
            st.state = FiveMState.ACTIVE_SETUP
            take_rec = {
                "setup_id": st.active_setup_id,
                "direction": d,
                "take_j": j,
                "take_price": m.m5_cl[j],
                "take_ts": str(m.m5_idx[j]),
                "signal_m1_i": int(m.m5_signal_m1_i[j]),
                "exec_m1_i": int(m.m5_close_m1_i[j]),
                "total_score": total,
                "15m_state": ctx15["state"],
                "15m_strength": ctx15["strength"],
                "reasons": "|".join(all_reasons),
                "entry_deterioration_atr": det,
                "tag": next((s["tag"] for s in st.setups if s["setup_id"] == st.active_setup_id), "CONTINUATION"),
            }
            st.takes.append(take_rec)
            self._log(j, st.state, dec, d, ctx15, struct, ctx15_score, loc["score"], react["score"], total, all_reasons + ["TAKE"])
            st.cooldown_remaining = cfg.get("cooldown_bars_5m", 3)
            st.state = FiveMState.COOLDOWN
            self._reset_armed()
            return st.decisions[-1]

        dec = FiveMDecision.REACTION if react["score"] >= 1 else FiveMDecision.WATCH
        return self._log(j, st.state, dec, d, ctx15, struct, ctx15_score, loc["score"], react["score"], total, all_reasons)

    def _structural_reset_allows(self, j: int, direction: str) -> bool:
        st = self.st
        if not st.active_setup_id and st.state == FiveMState.WATCH:
            return True
        if st.state == FiveMState.COOLDOWN:
            return False
        # New impulse in same direction after cooldown handled separately
        lb = min(j, 6)
        prog = self.m.m5_cl[j] - self.m.m5_cl[j - lb]
        if direction == "LONG" and prog > 0 and st.last_impulse_dir != "LONG":
            st.last_impulse_dir = "LONG"
            return True
        if direction == "SHORT" and prog < 0 and st.last_impulse_dir != "SHORT":
            st.last_impulse_dir = "SHORT"
            return True
        return st.state == FiveMState.WATCH

    def _setup_tag(self, ctx15: dict, direction: str) -> str:
        if direction == "LONG" and ctx15["state"] in ("BEARISH", "TRANSITION"):
            return "POTENTIAL_REVERSAL"
        if direction == "SHORT" and ctx15["state"] in ("BULLISH", "TRANSITION"):
            return "POTENTIAL_REVERSAL"
        return "CONTINUATION"

    def _invalidate(self, j: int, reason: str, ctx15: dict, struct: dict) -> None:
        self._log(j, FiveMState.WATCH, FiveMDecision.INVALIDATED, self.st.direction, ctx15, struct, 0, 0, 0, 0, [reason])
        self._reset_watch()

    def _pass(self, j: int, reason: str, ctx15: dict, struct: dict, c15, loc, react, contra, reasons) -> None:
        total = c15 + loc + react + contra
        self._log(j, FiveMState.WATCH, FiveMDecision.PASS, self.st.direction, ctx15, struct, c15, loc, react, total, reasons + [reason])
        self._reset_watch()

    def _reset_armed(self) -> None:
        self.st.direction = ""
        self.st.armed_j = -1
        self.st.armed_price = 0.0
        self.st.armed_bars = 0
        self.st.pb_extreme = 0.0
        self.st.active_setup_id = ""

    def _reset_watch(self) -> None:
        self._reset_armed()
        self.st.state = FiveMState.WATCH

    def _log(self, j, state, decision, direction, ctx15, struct, c15, loc, react, total, reasons) -> dict:
        rec = {
            "bar_j": j,
            "ts": str(self.m.m5_idx[j]),
            "5m_state": state.value if hasattr(state, "value") else state,
            "5m_decision": decision.value if hasattr(decision, "value") else decision,
            "direction": direction,
            "setup_id": self.st.active_setup_id,
            "15m_state": ctx15["state"],
            "15m_strength": ctx15["strength"],
            "15m_score": c15,
            "5m_struct_score": struct.get("score", 0),
            "5m_loc_score": loc,
            "5m_react_score": react,
            "5m_score": total,
            "reason_codes": "|".join(reasons),
        }
        self.st.decisions.append(rec)
        return rec

    def results(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        dec = pd.DataFrame(self.st.decisions) if self.st.decisions else pd.DataFrame()
        setups = pd.DataFrame(self.st.setups) if self.st.setups else pd.DataFrame()
        takes = pd.DataFrame(self.st.takes) if self.st.takes else pd.DataFrame()
        return dec, setups, takes


def _atr(val: float, arr: np.ndarray, j: int) -> float:
    if np.isfinite(val) and val > 0:
        return val
    for k in range(max(0, j - 5), j + 1):
        if np.isfinite(arr[k]) and arr[k] > 0:
            return arr[k]
    return 1.0


def _flat_15m() -> dict:
    return {"state": "NEUTRAL", "strength": 0.0, "bull": 0, "bear": 0, "score": 0, "reasons": [], "range_pos": 0.5, "impulse_atr": 0}
