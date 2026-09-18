"""Phase85 startup diagnostic. Does not send funded orders."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from phase85.config import load_phase85_config
from phase85.diagnostics.preflight import freeze_lines, funded_preflight, startup_banner
from phase85.execution.adapter import NinjaTraderExecutionAdapter
from phase85.execution.kill_switch import ExecutionKillSwitch, KillState
from phase85.ninjatrader.fake_bridge import FakeExecutionBridge


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase85 execution preflight")
    parser.add_argument("--fake", action="store_true", help="Use in-process fake bridge")
    args = parser.parse_args(argv)
    cfg = load_phase85_config()
    cfg.persistence_dir.mkdir(parents=True, exist_ok=True)
    print("\n".join(freeze_lines()))
    if not args.fake:
        print("EXECUTION_BRIDGE_NOT_ATTACHED")
        print(f"DEFAULT_MODE={cfg.execution_mode}")
        print("NEXT=start CRTExecutionBridge after unit/SIM gates or re-run with --fake")
        return 0
    bridge = FakeExecutionBridge(
        expected_token=cfg.execution_token or "missing",
        expected_account=cfg.expected_account or "SIM101",
        expected_instrument=cfg.expected_contract or "MNQ 12-26",
    )
    adapter = NinjaTraderExecutionAdapter(cfg, bridge, kill=ExecutionKillSwitch(KillState.EXECUTION_DISABLED))
    if cfg.execution_token:
        adapter.connect()
        adapter.startup_reconcile()
    for line in startup_banner(adapter):
        print(line)
    if cfg.execution_mode == "FUNDED":
        for line in funded_preflight(adapter):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
