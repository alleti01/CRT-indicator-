"""Unit tests — fail-closed defaults and gates."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase85.config import load_phase85_config
from phase85.execution.adapter import NinjaTraderExecutionAdapter, live_ready_config, make_intent
from phase85.execution.kill_switch import ExecutionKillSwitch, KillState
from phase85.ninjatrader.fake_bridge import FakeExecutionBridge
from phase85.tests.support import TOKEN, ready_funded, ready_sim


class SafetyDefaultTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def _attempt(self, cfg, **bridge_kw) -> str:
        bridge = FakeExecutionBridge(expected_token=TOKEN, expected_account=cfg.expected_account or "SIM101", **bridge_kw)
        adapter = NinjaTraderExecutionAdapter(cfg, bridge, kill=ExecutionKillSwitch(KillState.EXECUTION_ENABLED))
        adapter.connect()
        adapter.mark_data_healthy(True)
        adapter.startup_reconcile()
        return adapter.request_entry(make_intent()).reason

    def test_default_config_cannot_route(self) -> None:
        cfg = load_phase85_config(env=False)
        self.assertEqual(cfg.execution_mode, "SHADOW")
        self.assertTrue(cfg.shadow_mode)
        self.assertFalse(cfg.trading_enabled)
        self.assertFalse(cfg.external_order_routing)
        self.assertFalse(cfg.nt_execution_bridge_enabled)
        self.assertFalse(cfg.routing_enabled())

    def test_shadow_cannot_route(self) -> None:
        cfg = live_ready_config(self.tmp)
        cfg.execution_mode = "SHADOW"
        cfg.shadow_mode = True
        adapter = NinjaTraderExecutionAdapter(cfg, FakeExecutionBridge(expected_token=TOKEN, expected_account="SIM101"))
        adapter.connect()
        adapter.mark_data_healthy(True)
        adapter.startup_reconcile()
        result = adapter.request_entry(make_intent())
        self.assertFalse(result.allowed)
        self.assertTrue(result.would_enter or result.reason.startswith("WOULD") or not result.allowed)
        self.assertEqual(len(adapter.transport.submitted_commands), 0)

    def test_trading_enabled_false(self) -> None:
        cfg = live_ready_config(self.tmp)
        cfg.trading_enabled = False
        self.assertNotEqual(self._attempt(cfg), "ENTRY_COMMAND_SENT")

    def test_external_routing_false(self) -> None:
        cfg = live_ready_config(self.tmp)
        cfg.external_order_routing = False
        self.assertEqual(self._attempt(cfg), "EXTERNAL_ORDER_ROUTING_FALSE")

    def test_nt_bridge_disabled(self) -> None:
        cfg = live_ready_config(self.tmp)
        cfg.nt_execution_bridge_enabled = False
        self.assertEqual(self._attempt(cfg), "NT_EXECUTION_BRIDGE_DISABLED")

    def test_wrong_auth_cannot_route(self) -> None:
        cfg = live_ready_config(self.tmp)
        bridge = FakeExecutionBridge(expected_token="other", expected_account="SIM101")
        adapter = NinjaTraderExecutionAdapter(cfg, bridge, kill=ExecutionKillSwitch(KillState.EXECUTION_ENABLED))
        adapter.connect()
        adapter.mark_data_healthy(True)
        adapter.startup_reconcile()
        result = adapter.request_entry(make_intent())
        self.assertFalse(result.allowed)

    def test_wrong_account(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        adapter.cfg.expected_account = "NOT-THIS"
        result = adapter.request_entry(make_intent())
        self.assertEqual(result.reason, "REJECT_ACCOUNT_NOT_ALLOWED")

    def test_wrong_instrument(self) -> None:
        cfg = live_ready_config(self.tmp, contract="NQ 12-26")
        cfg.allowed_instrument_root = "MNQ"
        reason = self._attempt(cfg)
        self.assertEqual(reason, "REJECT_CONTRACT_MISMATCH")

    def test_quantity_gt_one(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        result = adapter.request_entry(make_intent(quantity=2))
        self.assertEqual(result.reason, "REJECT_MAX_QUANTITY")

    def test_bridge_rejects_qty_two_even_if_python_slipped(self) -> None:
        _, bridge = ready_sim(self.tmp)
        from phase85.protocol.messages import Command

        evs = bridge.send(Command(command="ENTER_LONG", command_id="q2", account="SIM101", instrument="MNQ 12-26", quantity=2))
        self.assertEqual(evs[0].reason, "REJECT_MAX_QUANTITY")

    def test_stale_signal(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        result = adapter.request_entry(make_intent(signal_age_seconds=500))
        self.assertEqual(result.reason, "PASS_STALE_SIGNAL")

    def test_unhealthy_data(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        adapter.mark_data_healthy(False)
        result = adapter.request_entry(make_intent())
        self.assertEqual(result.reason, "PASS_DATA_UNHEALTHY")

    def test_reconciliation_failure(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        bridge.inject_unexpected_position("LONG", 1)
        adapter.side = "FLAT"
        adapter.quantity = 0
        rec = adapter.startup_reconcile()
        self.assertFalse(rec.ok)
        result = adapter.request_entry(make_intent(signal_id="after-recon", event_id="after-recon"))
        self.assertEqual(result.reason, "RECONCILIATION_REQUIRED")

    def test_kill_switch(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        adapter.kill.disable()
        result = adapter.request_entry(make_intent())
        self.assertEqual(result.reason, "KILL_SWITCH")

    def test_no_auto_reverse(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        adapter.request_entry(make_intent(side="LONG", signal_id="long1", event_id="long1"))
        adapter.place_protection()
        result = adapter.request_entry(make_intent(side="SHORT", signal_id="short1", event_id="short1"))
        self.assertIn(result.reason, {"REJECT_NO_AUTO_REVERSE", "REJECT_POSITION_OPEN"})

    def test_funded_blocked_without_sim_gate(self) -> None:
        adapter, _ = ready_funded(self.tmp, sim_gate=False)
        result = adapter.request_entry(make_intent())
        self.assertEqual(result.reason, "SIM_GATE_NOT_PASS")

    def test_funded_requires_multi_arm(self) -> None:
        adapter, _ = ready_funded(self.tmp, sim_gate=True)
        adapter.cfg.trading_enabled = False
        result = adapter.request_entry(make_intent())
        self.assertFalse(result.allowed)
        self.assertNotEqual(result.reason, "ENTRY_COMMAND_SENT")

    def test_phase73_pass_no_order(self) -> None:
        adapter, _ = ready_sim(self.tmp)
        result = adapter.request_entry(make_intent(decision="PASS"))
        self.assertEqual(result.reason, "PHASE73_NOT_TAKE")
