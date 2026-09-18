"""Deterministic startup / funded preflight. Fail-closed."""
from __future__ import annotations

import hashlib
from pathlib import Path

from phase74.config.loader import verify_phase73_freeze
from phase85.config import CRTBARBRIDGE_RELPATH, FROZEN_PINE_HASH, Phase85Config
from phase85.execution.adapter import NinjaTraderExecutionAdapter
from phase85.execution.kill_switch import KillState

REPO = Path(__file__).resolve().parents[2]


def pine_hash() -> str:
    path = REPO / "TV_REVIEW" / "phase72a_autonomous_trader.pine"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def crtbarbridge_unchanged() -> bool:
    text = (REPO / CRTBARBRIDGE_RELPATH).read_text(encoding="utf-8", errors="replace")
    forbidden = ("CreateOrder", "Account.Submit", "EnterLong", "EnterShort", "Flatten(")
    return not any(tok in text for tok in forbidden)


def freeze_lines() -> list[str]:
    lines: list[str] = []
    h = pine_hash()
    lines.append("PHASE72A_FREEZE_OK" if h == FROZEN_PINE_HASH else "PHASE85_FREEZE_VIOLATION")
    ok, _ = verify_phase73_freeze()
    lines.append("PHASE73_FREEZE_OK" if ok else "PHASE73_FREEZE_FAIL")
    return lines


def startup_banner(adapter: NinjaTraderExecutionAdapter) -> list[str]:
    cfg = adapter.cfg
    lines = freeze_lines()
    if adapter.data_healthy:
        lines.append("NINJATRADER_DATA_CONNECTED")
        lines.append("DATA_HEALTHY")
    else:
        lines.append("DATA_UNHEALTHY")
    lines.append(f"EXECUTION_MODE={cfg.execution_mode}")
    if cfg.execution_mode == "SHADOW" or cfg.shadow_mode or not cfg.routing_enabled():
        lines.append("EXECUTION_DISABLED_EXTERNAL")
        lines.append("TRADER_READY_SHADOW")
        return lines
    if adapter.transport.connected:
        lines.append("EXECUTION_BRIDGE_CONNECTED")
    if adapter.transport.authenticated:
        lines.append("EXECUTION_AUTHENTICATED")
    if adapter.transport.account_verified:
        key = "FUNDED_ACCOUNT_VERIFIED" if cfg.execution_mode == "FUNDED" else "SIM_ACCOUNT_VERIFIED"
        lines.append(key)
    if adapter.transport.contract_verified:
        lines.append("CONTRACT_VERIFIED")
    if adapter.position_reconciled:
        lines.append("POSITION_RECONCILED")
    if adapter.orders_reconciled:
        lines.append("ORDERS_RECONCILED")
    if cfg.execution_mode == "SIM":
        lines.append("EXECUTION_READY_SIM")
    if cfg.execution_mode == "FUNDED":
        lines.extend(funded_preflight(adapter))
    return lines


def funded_preflight(adapter: NinjaTraderExecutionAdapter) -> list[str]:
    cfg = adapter.cfg
    required_ok = True
    lines: list[str] = []

    def add(ok: bool, good: str, bad: str) -> None:
        nonlocal required_ok
        lines.append(good if ok else bad)
        if not ok:
            required_ok = False

    h = pine_hash()
    add(h == FROZEN_PINE_HASH, "PHASE72A_FREEZE_OK", "PHASE85_FREEZE_VIOLATION")
    p73, _ = verify_phase73_freeze()
    add(p73, "PHASE73_FREEZE_OK", "PHASE73_FREEZE_FAIL")
    add(adapter.data_healthy, "NINJATRADER_DATA_CONNECTED", "DATA_UNHEALTHY")
    if adapter.data_healthy:
        lines.append("DATA_HEALTHY")
    add(adapter.transport.connected, "EXECUTION_BRIDGE_CONNECTED", "EXECUTION_BRIDGE_DISCONNECTED")
    add(adapter.transport.authenticated, "EXECUTION_AUTHENTICATED", "EXECUTION_NOT_AUTHENTICATED")
    add(cfg.execution_mode == "FUNDED", "EXECUTION_MODE=FUNDED", f"EXECUTION_MODE={cfg.execution_mode}")
    add(cfg.funded_account_verified and cfg.allowed_funded_account == cfg.expected_account, "FUNDED_ACCOUNT_VERIFIED", "FUNDED_ACCOUNT_NOT_VERIFIED")
    lines.append(f"CONTRACT={cfg.allowed_instrument_root}")
    add(adapter.transport.contract_verified, "CONTRACT_VERIFIED", "CONTRACT_UNVERIFIED")
    add(cfg.max_quantity == 1, "MAX_QUANTITY=1", f"MAX_QUANTITY={cfg.max_quantity}")
    add(adapter.position_reconciled and adapter.side == "FLAT", "POSITION_RECONCILED", "POSITION_NOT_RECONCILED")
    if adapter.side == "FLAT":
        lines.append("POSITION=FLAT")
    snap = adapter.transport.snapshot()
    add(adapter.orders_reconciled and int(snap.get("working_orders", 0) or 0) == 0, "ORDERS_RECONCILED", "ORDERS_NOT_RECONCILED")
    lines.append(f"UNEXPECTED_WORKING_ORDERS={int(snap.get('unexpected_orders', 0) or 0)}")
    add(adapter.kill.state is not KillState.EXECUTION_HALTED, "KILL_SWITCH=OFF", "KILL_SWITCH=HALTED")
    add(cfg.trading_enabled, "TRADING_ENABLED=TRUE", "TRADING_ENABLED=FALSE")
    add(cfg.external_order_routing, "EXTERNAL_ORDER_ROUTING=TRUE", "EXTERNAL_ORDER_ROUTING=FALSE")
    add(cfg.nt_execution_bridge_enabled, "NT_EXECUTION_BRIDGE_ENABLED=TRUE", "NT_EXECUTION_BRIDGE_ENABLED=FALSE")
    add(adapter.sim_gate_pass, "SIM_GATE=PASS", "SIM_GATE=FAIL")
    if required_ok:
        lines.append("FUNDED_EXECUTION_READY")
    else:
        lines.append("FUNDED_EXECUTION_NOT_READY")
    return lines
