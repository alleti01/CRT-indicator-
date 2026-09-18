"""Unit tests — webhook + command idempotency."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from phase85.execution.adapter import NinjaTraderExecutionAdapter, live_ready_config, make_intent
from phase85.execution.kill_switch import ExecutionKillSwitch, KillState
from phase85.ninjatrader.fake_bridge import FakeExecutionBridge
from phase85.tests.support import TOKEN, ready_sim


class DuplicateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def test_same_webhook_four_times_one_entry(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        cid = "cmd-fixed"
        results = []
        for _ in range(4):
            results.append(
                adapter.request_entry(
                    make_intent(command_id=cid, signal_id="sig-fixed", event_id="evt-fixed")
                )
            )
        enters = [c for c in bridge.submitted_commands if c.command.startswith("ENTER_")]
        self.assertEqual(len(enters), 1)
        self.assertTrue(results[0].allowed)
        self.assertTrue(all(r.reason in {"DUPLICATE_COMMAND", "DUPLICATE_SIGNAL"} for r in results[1:]))

    def test_same_command_four_times_one_nt_entry(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        intent = make_intent(command_id="abc", signal_id="s-abc", event_id="e-abc")
        adapter.request_entry(intent)
        for i in range(3):
            adapter.request_entry(make_intent(command_id="abc", signal_id=f"other{i}", event_id=f"o{i}"))
        self.assertEqual(sum(1 for c in bridge.submitted_commands if c.command.startswith("ENTER_")), 1)

    def test_restart_python_replay_command(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        intent = make_intent(command_id="persist-1", signal_id="sp1", event_id="ep1")
        adapter.request_entry(intent)
        cfg = live_ready_config(self.tmp)
        bridge2 = FakeExecutionBridge(expected_token=TOKEN, expected_account="SIM101", expected_instrument="MNQ 12-26")
        adapter2 = NinjaTraderExecutionAdapter(cfg, bridge2, kill=ExecutionKillSwitch(KillState.EXECUTION_ENABLED))
        adapter2.connect()
        adapter2.mark_data_healthy(True)
        adapter2.startup_reconcile()
        # Python believed FLAT after fresh start; NT fake is also FLAT — but command_id persists
        again = adapter2.request_entry(intent)
        self.assertEqual(again.reason, "DUPLICATE_COMMAND")
        self.assertEqual(sum(1 for c in bridge2.submitted_commands if c.command.startswith("ENTER_")), 0)

    def test_restart_bridge_replay_known_command(self) -> None:
        adapter, bridge = ready_sim(self.tmp)
        cmd_id = "bridge-persist"
        adapter.request_entry(make_intent(command_id=cmd_id, signal_id="sb1", event_id="eb1"))
        from phase85.protocol.messages import Command

        events = bridge.send(
            Command(command="ENTER_LONG", command_id=cmd_id, account="SIM101", instrument="MNQ 12-26", quantity=1)
        )
        self.assertEqual(events[0].event, "DUPLICATE_COMMAND")
        self.assertEqual(sum(1 for c in bridge.submitted_commands if c.command.startswith("ENTER_")), 1)
