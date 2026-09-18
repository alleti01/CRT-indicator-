"""State machine transition guards."""
from __future__ import annotations

import unittest

from phase85.execution.state_machine import ExecutionState, ExecutionStateMachine, InvalidTransition


class StateMachineTests(unittest.TestCase):
    def test_idle_cannot_target_filled(self) -> None:
        fsm = ExecutionStateMachine()
        with self.assertRaises(InvalidTransition):
            fsm.transition(ExecutionState.EXIT_PENDING)
        self.assertEqual(fsm.state, ExecutionState.IDLE)

    def test_happy_path(self) -> None:
        fsm = ExecutionStateMachine()
        fsm.transition(ExecutionState.ENTRY_PENDING)
        fsm.transition(ExecutionState.ENTRY_ACCEPTED)
        fsm.transition(ExecutionState.FILLED_UNPROTECTED)
        fsm.transition(ExecutionState.PROTECTION_PENDING)
        fsm.transition(ExecutionState.POSITION_PROTECTED)
        fsm.transition(ExecutionState.EXIT_PENDING)
        fsm.transition(ExecutionState.FLAT)
        fsm.transition(ExecutionState.IDLE)

    def test_halted_stays_halted(self) -> None:
        fsm = ExecutionStateMachine(ExecutionState.HALTED)
        self.assertEqual(fsm.transition(ExecutionState.HALTED), ExecutionState.HALTED)
        with self.assertRaises(InvalidTransition):
            fsm.transition(ExecutionState.IDLE)
