"""Unit tests — disconnect safety."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase85.execution.adapter import make_intent
from phase85.execution.state_machine import ExecutionState
from phase85.tests.support import ready_sim


class DisconnectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_market_data_lost_blocks_entries(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        adapter.mark_data_healthy(False)
        result = adapter.request_entry(make_intent())
        self.assertEqual(result.reason, "PASS_DATA_UNHEALTHY")

    def test_execution_bridge_lost_blocks_entries(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        adapter.request_entry(make_intent(signal_id="d1", event_id="d1"))
        adapter.place_protection()
        self.assertEqual(adapter.state, ExecutionState.POSITION_PROTECTED)
        stop_before = adapter.stop_working
        target_before = adapter.target_working
        bridge.disconnect()
        blocked = adapter.request_entry(make_intent(signal_id="d2", event_id="d2"))
        self.assertFalse(blocked.allowed)
        self.assertTrue(stop_before and target_before)
        self.assertTrue(adapter.stop_working)
        self.assertTrue(adapter.target_working)

    def test_protect_then_disconnect_does_not_cancel_protection(self) -> None:
        adapter, bridge = ready_sim(self.tmp, disconnected_after_protect=True)
        adapter.request_entry(make_intent(signal_id="p1", event_id="p1"))
        adapter.place_protection()
        self.assertTrue(adapter.stop_working)
        self.assertTrue(adapter.target_working)
        self.assertFalse(bridge.connected)
        snap = bridge.snapshot()
        # snapshot connected flag false, but working orders remain
        self.assertTrue(any(o.kind == "STOP" and o.state == "WORKING" for o in bridge.orders.values()))
        self.assertTrue(any(o.kind == "TARGET" and o.state == "WORKING" for o in bridge.orders.values()))

    def test_reconnect_requires_reconcile(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        bridge.disconnect()
        self.assertFalse(adapter.request_entry(make_intent(signal_id="r1", event_id="r1")).allowed)
        bridge.connect("unit-test-execution-token")
        adapter.startup_reconcile()
        self.assertTrue(adapter.startup_reconciled)
        ok = adapter.request_entry(make_intent(signal_id="r2", event_id="r2"))
        self.assertTrue(ok.allowed)
