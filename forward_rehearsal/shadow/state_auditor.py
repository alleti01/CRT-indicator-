"""Shadow/engine state machine invariant auditor."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from phase73.trader.fsm import TraderState


class ShadowState(str, Enum):
    SHADOW_FLAT = "SHADOW_FLAT"
    SHADOW_SIGNAL_RECEIVED = "SHADOW_SIGNAL_RECEIVED"
    SHADOW_ENTRY_CHECK = "SHADOW_ENTRY_CHECK"
    SHADOW_ACTIVE_LONG = "SHADOW_ACTIVE_LONG"
    SHADOW_ACTIVE_SHORT = "SHADOW_ACTIVE_SHORT"
    SHADOW_EXIT_PENDING = "SHADOW_EXIT_PENDING"
    SHADOW_HALTED = "SHADOW_HALTED"


ALLOWED_SHADOW_TRANSITIONS: dict[ShadowState, set[ShadowState]] = {
    ShadowState.SHADOW_FLAT: {
        ShadowState.SHADOW_SIGNAL_RECEIVED,
        ShadowState.SHADOW_ENTRY_CHECK,
        ShadowState.SHADOW_HALTED,
    },
    ShadowState.SHADOW_SIGNAL_RECEIVED: {
        ShadowState.SHADOW_ENTRY_CHECK,
        ShadowState.SHADOW_FLAT,
        ShadowState.SHADOW_ACTIVE_LONG,
        ShadowState.SHADOW_ACTIVE_SHORT,
        ShadowState.SHADOW_HALTED,
    },
    ShadowState.SHADOW_ENTRY_CHECK: {
        ShadowState.SHADOW_FLAT,
        ShadowState.SHADOW_ACTIVE_LONG,
        ShadowState.SHADOW_ACTIVE_SHORT,
        ShadowState.SHADOW_HALTED,
    },
    ShadowState.SHADOW_ACTIVE_LONG: {
        ShadowState.SHADOW_FLAT,
        ShadowState.SHADOW_EXIT_PENDING,
        ShadowState.SHADOW_SIGNAL_RECEIVED,
        ShadowState.SHADOW_HALTED,
    },
    ShadowState.SHADOW_ACTIVE_SHORT: {
        ShadowState.SHADOW_FLAT,
        ShadowState.SHADOW_EXIT_PENDING,
        ShadowState.SHADOW_SIGNAL_RECEIVED,
        ShadowState.SHADOW_HALTED,
    },
    ShadowState.SHADOW_EXIT_PENDING: {ShadowState.SHADOW_FLAT, ShadowState.SHADOW_HALTED},
    ShadowState.SHADOW_HALTED: {ShadowState.SHADOW_FLAT, ShadowState.SHADOW_HALTED},
}


@dataclass
class StateInvariantFailure:
    from_state: str
    to_state: str
    trigger: str
    detail: str


@dataclass
class StateMachineAuditor:
    shadow_state: ShadowState = ShadowState.SHADOW_FLAT
    engine_state: str = TraderState.FLAT.value
    failures: list[StateInvariantFailure] = field(default_factory=list)
    halted: bool = False

    def record_engine_state(self, state: TraderState | str) -> None:
        self.engine_state = state.value if isinstance(state, TraderState) else str(state)

    def transition_shadow(self, new_state: ShadowState, *, trigger: str, detail: str = "") -> bool:
        if self.halted:
            return False
        allowed = ALLOWED_SHADOW_TRANSITIONS.get(self.shadow_state, set())
        if new_state not in allowed and new_state != self.shadow_state:
            self.failures.append(
                StateInvariantFailure(self.shadow_state.value, new_state.value, trigger, detail or "disallowed transition")
            )
            self.halted = True
            self.shadow_state = ShadowState.SHADOW_HALTED
            return False
        self.shadow_state = new_state
        return True

    def map_shadow_action(self, action: str, direction: str = "") -> ShadowState:
        if action.startswith("WOULD_ENTER_LONG"):
            return ShadowState.SHADOW_ACTIVE_LONG
        if action.startswith("WOULD_ENTER_SHORT"):
            return ShadowState.SHADOW_ACTIVE_SHORT
        if action.startswith("WOULD_EXIT"):
            return ShadowState.SHADOW_EXIT_PENDING
        if action.startswith("WOULD_PASS") or action.startswith("WOULD_WATCH"):
            return ShadowState.SHADOW_FLAT
        if action.startswith("WOULD_HOLD"):
            return ShadowState.SHADOW_ACTIVE_LONG if "LONG" in action else ShadowState.SHADOW_ACTIVE_SHORT
        if "SIGNAL" in action:
            return ShadowState.SHADOW_SIGNAL_RECEIVED
        return self.shadow_state

    def apply_action(self, action: str, *, trigger: str, direction: str = "") -> None:
        target = self.map_shadow_action(action, direction)
        if action.startswith("WOULD_EXIT"):
            self.transition_shadow(ShadowState.SHADOW_EXIT_PENDING, trigger=trigger, detail=action)
            self.transition_shadow(ShadowState.SHADOW_FLAT, trigger=trigger, detail="exit complete")
        elif action.startswith("WOULD_ENTER"):
            self.transition_shadow(ShadowState.SHADOW_SIGNAL_RECEIVED, trigger=trigger)
            self.transition_shadow(ShadowState.SHADOW_ENTRY_CHECK, trigger=trigger)
            self.transition_shadow(target, trigger=trigger, detail=action)
        elif action.startswith("WOULD_PASS"):
            self.transition_shadow(ShadowState.SHADOW_SIGNAL_RECEIVED, trigger=trigger)
            self.transition_shadow(ShadowState.SHADOW_FLAT, trigger=trigger, detail=action)
        elif action.startswith("WOULD_HOLD"):
            self.transition_shadow(target, trigger=trigger, detail=action)

    def summary(self) -> dict[str, Any]:
        return {
            "shadow_state": self.shadow_state.value,
            "engine_state": self.engine_state,
            "state_invariant_failures": len(self.failures),
            "halted": self.halted,
        }
