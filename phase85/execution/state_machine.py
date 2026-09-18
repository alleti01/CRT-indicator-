"""Deterministic execution state machine. Impossible transitions are rejected."""
from __future__ import annotations

from enum import Enum


class ExecutionState(str, Enum):
    IDLE = "IDLE"
    ENTRY_PENDING = "ENTRY_PENDING"
    ENTRY_ACCEPTED = "ENTRY_ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED_UNPROTECTED = "FILLED_UNPROTECTED"
    PROTECTION_PENDING = "PROTECTION_PENDING"
    POSITION_PROTECTED = "POSITION_PROTECTED"
    EXIT_PENDING = "EXIT_PENDING"
    FLATTENING = "FLATTENING"
    FLAT = "FLAT"
    REJECTED = "REJECTED"
    PROTECTION_FAILURE = "PROTECTION_FAILURE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    HALTED = "HALTED"


ALLOWED_TRANSITIONS: dict[ExecutionState, frozenset[ExecutionState]] = {
    ExecutionState.IDLE: frozenset(
        {
            ExecutionState.ENTRY_PENDING,
            ExecutionState.REJECTED,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
            ExecutionState.FLAT,
        }
    ),
    ExecutionState.ENTRY_PENDING: frozenset(
        {
            ExecutionState.ENTRY_ACCEPTED,
            ExecutionState.PARTIALLY_FILLED,
            ExecutionState.FILLED_UNPROTECTED,
            ExecutionState.REJECTED,
            ExecutionState.IDLE,
            ExecutionState.FLATTENING,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.ENTRY_ACCEPTED: frozenset(
        {
            ExecutionState.PARTIALLY_FILLED,
            ExecutionState.FILLED_UNPROTECTED,
            ExecutionState.REJECTED,
            ExecutionState.IDLE,
            ExecutionState.FLATTENING,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.PARTIALLY_FILLED: frozenset(
        {
            ExecutionState.PARTIALLY_FILLED,
            ExecutionState.FILLED_UNPROTECTED,
            ExecutionState.FLATTENING,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.FILLED_UNPROTECTED: frozenset(
        {
            ExecutionState.PROTECTION_PENDING,
            ExecutionState.PROTECTION_FAILURE,
            ExecutionState.FLATTENING,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.PROTECTION_PENDING: frozenset(
        {
            ExecutionState.POSITION_PROTECTED,
            ExecutionState.PROTECTION_FAILURE,
            ExecutionState.FLATTENING,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.POSITION_PROTECTED: frozenset(
        {
            ExecutionState.EXIT_PENDING,
            ExecutionState.FLATTENING,
            ExecutionState.FLAT,
            ExecutionState.PROTECTION_FAILURE,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.EXIT_PENDING: frozenset(
        {
            ExecutionState.FLAT,
            ExecutionState.FLATTENING,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.FLATTENING: frozenset(
        {
            ExecutionState.FLAT,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.FLAT: frozenset(
        {
            ExecutionState.IDLE,
            ExecutionState.RECONCILIATION_REQUIRED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.REJECTED: frozenset(
        {
            ExecutionState.IDLE,
            ExecutionState.HALTED,
            ExecutionState.RECONCILIATION_REQUIRED,
        }
    ),
    ExecutionState.PROTECTION_FAILURE: frozenset(
        {
            ExecutionState.FLATTENING,
            ExecutionState.FLAT,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.RECONCILIATION_REQUIRED: frozenset(
        {
            ExecutionState.IDLE,
            ExecutionState.FLAT,
            ExecutionState.POSITION_PROTECTED,
            ExecutionState.FILLED_UNPROTECTED,
            ExecutionState.HALTED,
        }
    ),
    ExecutionState.HALTED: frozenset({ExecutionState.HALTED}),
}


class InvalidTransition(ValueError):
    def __init__(self, src: ExecutionState, dst: ExecutionState) -> None:
        super().__init__(f"INVALID_TRANSITION {src.value}->{dst.value}")
        self.src = src
        self.dst = dst


class ExecutionStateMachine:
    def __init__(self, state: ExecutionState = ExecutionState.IDLE) -> None:
        self.state = state
        self.invalid_attempts: list[str] = []

    def can(self, dst: ExecutionState) -> bool:
        return dst in ALLOWED_TRANSITIONS[self.state]

    def transition(self, dst: ExecutionState) -> ExecutionState:
        if dst == self.state and dst in {
            ExecutionState.PARTIALLY_FILLED,
            ExecutionState.HALTED,
        }:
            return self.state
        if not self.can(dst):
            label = f"{self.state.value}->{dst.value}"
            self.invalid_attempts.append(label)
            raise InvalidTransition(self.state, dst)
        self.state = dst
        return self.state
