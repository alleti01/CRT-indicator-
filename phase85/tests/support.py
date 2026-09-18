"""Shared test helpers."""
from __future__ import annotations

from pathlib import Path

from phase85.execution.adapter import NinjaTraderExecutionAdapter, live_ready_config, make_intent
from phase85.execution.kill_switch import ExecutionKillSwitch, KillState
from phase85.ninjatrader.fake_bridge import FakeExecutionBridge


TOKEN = "unit-test-execution-token"


def write_sim_gate(path: Path, passed: bool = True) -> None:
    path.write_text(
        '{"pass": %s, "verdict": "%s"}\n'
        % (
            "true" if passed else "false",
            "PHASE85_SIM_EXECUTION_PASS" if passed else "PHASE85_SIM_EXECUTION_FAIL",
        )
    )


def ready_sim(tmp: Path, **bridge_kw) -> tuple[NinjaTraderExecutionAdapter, FakeExecutionBridge]:
    cfg = live_ready_config(tmp)
    bridge = FakeExecutionBridge(expected_token=TOKEN, expected_account="SIM101", expected_instrument="MNQ 12-26", **bridge_kw)
    adapter = NinjaTraderExecutionAdapter(cfg, bridge, kill=ExecutionKillSwitch(KillState.EXECUTION_ENABLED))
    adapter.connect()
    adapter.mark_data_healthy(True)
    adapter.startup_reconcile()
    return adapter, bridge


def ready_funded(tmp: Path, *, sim_gate: bool = False, **bridge_kw) -> tuple[NinjaTraderExecutionAdapter, FakeExecutionBridge]:
    if sim_gate:
        write_sim_gate(tmp / "sim_activation_gate.json", True)
    cfg = live_ready_config(
        tmp,
        mode="FUNDED",
        account="FUNDED99",
        funded_account="FUNDED99",
        funded_verified=True,
    )
    bridge = FakeExecutionBridge(expected_token=TOKEN, expected_account="FUNDED99", expected_instrument="MNQ 12-26", **bridge_kw)
    adapter = NinjaTraderExecutionAdapter(cfg, bridge, kill=ExecutionKillSwitch(KillState.EXECUTION_ENABLED))
    adapter.connect()
    adapter.mark_data_healthy(True)
    adapter.startup_reconcile()
    return adapter, bridge
