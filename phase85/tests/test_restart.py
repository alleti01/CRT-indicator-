"""Unit tests — restart reconciliation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase85.execution.adapter import NinjaTraderExecutionAdapter, live_ready_config, make_intent
from phase85.execution.kill_switch import ExecutionKillSwitch, KillState
from phase85.execution.state_machine import ExecutionState
from phase85.ninjatrader.fake_bridge import FakeExecutionBridge
from phase85.tests.support import TOKEN, ready_sim


def _resume(tmp: Path, bridge: FakeExecutionBridge) -> NinjaTraderExecutionAdapter:
    cfg = live_ready_config(tmp)
    adapter = NinjaTraderExecutionAdapter(cfg, bridge, kill=ExecutionKillSwitch(KillState.EXECUTION_ENABLED))
    adapter.connect()
    adapter.mark_data_healthy(True)
    adapter.startup_reconcile()
    return adapter


class RestartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_flat_restart(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        resumed = _resume(self.tmp, bridge)
        self.assertTrue(resumed.startup_reconciled)
        self.assertEqual(resumed.side, "FLAT")
        ok = resumed.request_entry(make_intent(signal_id="after-flat", event_id="after-flat"))
        self.assertTrue(ok.allowed)

    def test_entry_pending_restart_blocks_until_reconcile(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        adapter.fsm.state = ExecutionState.ENTRY_PENDING
        resumed = _resume(self.tmp, bridge)
        # NT is flat; Python idle after new process. Startup reconcile should pass FLAT.
        self.assertTrue(resumed.startup_reconciled)

    def test_filled_unprotected_restart(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        adapter.request_entry(make_intent(signal_id="u1", event_id="u1"))
        # new python process, NT still long unprotected
        cfg = live_ready_config(self.tmp)
        fresh = NinjaTraderExecutionAdapter(cfg, bridge, kill=ExecutionKillSwitch(KillState.EXECUTION_ENABLED))
        fresh.connect()
        fresh.mark_data_healthy(True)
        rec = fresh.startup_reconcile()
        self.assertFalse(rec.ok)
        blocked = fresh.request_entry(make_intent(signal_id="u2", event_id="u2"))
        self.assertEqual(blocked.reason, "RECONCILIATION_REQUIRED")

    def test_position_protected_restart(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        adapter.request_entry(make_intent(signal_id="p1", event_id="p1"))
        adapter.place_protection()
        cfg = live_ready_config(self.tmp)
        fresh = NinjaTraderExecutionAdapter(cfg, bridge, kill=ExecutionKillSwitch(KillState.EXECUTION_ENABLED))
        fresh.connect()
        fresh.mark_data_healthy(True)
        rec = fresh.startup_reconcile()
        # Python expected FLAT, NT long protected → mismatch
        self.assertFalse(rec.ok)
        self.assertEqual(fresh.state, ExecutionState.RECONCILIATION_REQUIRED)

    def test_post_stop_restart(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        adapter.request_entry(make_intent(signal_id="st1", event_id="st1"))
        adapter.place_protection()
        adapter.apply_external_events(bridge.fill_stop())
        resumed = _resume(self.tmp, bridge)
        self.assertTrue(resumed.startup_reconciled)
        self.assertEqual(resumed.side, "FLAT")

    def test_post_target_restart(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        adapter.request_entry(make_intent(signal_id="tg1", event_id="tg1"))
        adapter.place_protection()
        adapter.apply_external_events(bridge.fill_target())
        resumed = _resume(self.tmp, bridge)
        self.assertTrue(resumed.startup_reconciled)

    def test_unexpected_position_restart(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        bridge.inject_unexpected_position("SHORT", 1)
        rec = adapter.startup_reconcile()
        self.assertFalse(rec.ok)
        self.assertIn("UNEXPECTED_POSITION", rec.mismatches)
        self.assertEqual(adapter.request_entry(make_intent(signal_id="x1", event_id="x1")).reason, "RECONCILIATION_REQUIRED")

    def test_orphan_order_restart(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        bridge.inject_orphan_order()
        rec = adapter.startup_reconcile()
        self.assertFalse(rec.ok)
        self.assertIn("ORPHAN_ORDER", rec.mismatches)
        self.assertFalse(adapter.request_entry(make_intent(signal_id="or1", event_id="or1")).allowed)
