"""Unit tests — execution lifecycle."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase85.execution.adapter import make_intent
from phase85.execution.kill_switch import KillState
from phase85.execution.state_machine import ExecutionState, InvalidTransition
from phase85.tests.support import ready_sim


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_enter_target_flat(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        intent = make_intent(side="LONG", signal_id="l1", event_id="e1")
        result = adapter.request_entry(intent)
        self.assertTrue(result.allowed)
        self.assertEqual(adapter.state, ExecutionState.FILLED_UNPROTECTED)
        self.assertIsNotNone(adapter.actual_fill)
        self.assertEqual(adapter.actual_fill, bridge.fill_price)
        self.assertNotEqual(adapter.actual_fill, intent.expected_entry)
        prot = adapter.place_protection()
        self.assertTrue(prot.allowed)
        self.assertEqual(adapter.state, ExecutionState.POSITION_PROTECTED)
        self.assertTrue(adapter.stop_working)
        self.assertTrue(adapter.target_working)
        adapter.apply_external_events(bridge.fill_target())
        self.assertEqual(adapter.side, "FLAT")
        self.assertEqual(adapter.state, ExecutionState.IDLE)

    def test_enter_stop_flat(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        adapter.request_entry(make_intent(side="SHORT", signal_id="s1", event_id="es1"))
        adapter.place_protection()
        adapter.apply_external_events(bridge.fill_stop())
        self.assertEqual(adapter.side, "FLAT")
        self.assertEqual(adapter.state, ExecutionState.IDLE)

    def test_enter_rejected(self) -> None:
        adapter, _ = ready_sim(self.tmp, reject_next_entry=True)
        result = adapter.request_entry(make_intent())
        self.assertTrue(result.allowed)
        self.assertEqual(adapter.state, ExecutionState.IDLE)
        self.assertEqual(adapter.side, "FLAT")

    def test_partial_fill_then_full(self) -> None:
        adapter, bridge = ready_sim(self.tmp, partial_then_fill=True)
        # architecture must accept remaining_quantity updates even at qty=1
        adapter.request_entry(make_intent(quantity=1))
        self.assertGreaterEqual(adapter.filled_qty, 1)
        adapter.place_protection(quantity=adapter.filled_qty)
        self.assertLessEqual(adapter.filled_qty, 1)
        self.assertTrue(adapter.stop_working)

    def test_protection_failure_flatten_halt(self) -> None:
        adapter, _ = ready_sim(self.tmp, protection_should_fail=True)
        adapter.request_entry(make_intent(signal_id="pf1", event_id="pf1"))
        adapter.place_protection()
        self.assertEqual(adapter.kill.state, KillState.EXECUTION_HALTED)
        self.assertEqual(adapter.state, ExecutionState.HALTED)
        self.assertTrue(adapter.flatten_confirmed)
        blocked = adapter.request_entry(make_intent(signal_id="pf2", event_id="pf2", command_id="other"))
        self.assertFalse(blocked.allowed)
        self.assertIn(blocked.reason, {"EXECUTION_HALTED", "KILL_SWITCH"})

    def test_invalid_idle_to_target_filled(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        from phase85.protocol.messages import Event

        adapter.apply_external_events([Event(event="TARGET_FILLED", fill_price=1.0)])
        self.assertEqual(adapter.state, ExecutionState.IDLE)
        self.assertTrue(any(e["event"] == "INVALID_TRANSITION" for e in adapter.audit.events))

    def test_m0_from_actual_fill(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        bridge.fill_price = 20100.0
        adapter.request_entry(make_intent(expected_entry=20000.0, signal_atr=10.0))
        self.assertIsNotNone(adapter.last_m0)
        self.assertEqual(adapter.last_m0.actual_fill, 20100.0)
        self.assertAlmostEqual(adapter.last_m0.stop_price, 20100.0 - 10.0)
        self.assertAlmostEqual(adapter.last_m0.target_price, 20100.0 + 25.0)
        self.assertAlmostEqual(adapter.last_m0.slippage_points, 100.0)
        self.assertAlmostEqual(adapter.last_m0.slippage_ticks, 400.0)

    def test_protection_qty_cannot_exceed_fill(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        adapter.request_entry(make_intent())
        result = adapter.place_protection(quantity=2)
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "INVALID_QUANTITY")

    def test_flatten_requires_position_flat_event(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        adapter.request_entry(make_intent(signal_id="fl1", event_id="fl1"))
        adapter.place_protection()
        result = adapter.flatten()
        self.assertTrue(result.allowed)
        self.assertEqual(result.reason, "FLAT")
        self.assertEqual(adapter.side, "FLAT")


if __name__ == "__main__":
    unittest.main()
