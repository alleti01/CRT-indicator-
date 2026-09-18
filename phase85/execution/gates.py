"""Fail-closed safety gates. Any failure means NO ORDER."""
from __future__ import annotations

from dataclasses import dataclass, field

from phase85.config import Phase85Config
from phase85.execution.kill_switch import ExecutionKillSwitch, KillState
from phase85.execution.state_machine import ExecutionState


@dataclass
class GateContext:
    cfg: Phase85Config
    kill: ExecutionKillSwitch
    phase73_decision: str = "PASS"
    data_healthy: bool = False
    bridge_connected: bool = False
    bridge_authenticated: bool = False
    account_verified: bool = False
    connected_account: str = ""
    contract_verified: bool = False
    contract_name: str = ""
    quantity: int = 1
    command_duplicate: bool = False
    signal_duplicate: bool = False
    signal_stale: bool = False
    position_reconciled: bool = False
    orders_reconciled: bool = False
    startup_reconciled: bool = False
    open_strategy_positions: int = 0
    existing_side: str = "FLAT"
    intended_side: str = ""
    sim_gate_pass: bool = False
    unresolved_halt: bool = False
    unresolved_reconciliation: bool = False
    extra_failed: str = ""


@dataclass
class GateResult:
    allowed: bool
    reason: str
    failed: list[str] = field(default_factory=list)

    @staticmethod
    def ok() -> "GateResult":
        return GateResult(True, "GATES_PASS")

    @staticmethod
    def deny(reason: str) -> "GateResult":
        return GateResult(False, reason, [reason])


def _instrument_allowed(cfg: Phase85Config, contract_name: str) -> bool:
    root = (contract_name or cfg.allowed_instrument_root or "").upper().split()[0]
    if root == "NQ" and not cfg.allow_nq_execution:
        return False
    if cfg.allowed_instrument_root and root != cfg.allowed_instrument_root:
        return False
    if cfg.expected_contract and contract_name and contract_name != cfg.expected_contract:
        return False
    return True


def evaluate_entry_gates(ctx: GateContext) -> GateResult:
    cfg = ctx.cfg
    failed: list[str] = []

    if cfg.execution_mode not in {"SHADOW", "SIM", "FUNDED"}:
        failed.append("INVALID_CONFIG")
    if not cfg.trading_enabled:
        failed.append("TRADING_ENABLED_FALSE")
    if not cfg.external_order_routing:
        failed.append("EXTERNAL_ORDER_ROUTING_FALSE")
    if not cfg.nt_execution_bridge_enabled:
        failed.append("NT_EXECUTION_BRIDGE_DISABLED")
    if cfg.shadow_mode:
        failed.append("SHADOW_MODE")
    if cfg.execution_mode == "SHADOW":
        failed.append("EXECUTION_MODE_SHADOW")
    if cfg.execution_mode not in {"SIM", "FUNDED"}:
        failed.append("EXECUTION_MODE_NOT_LIVE")
    if ctx.phase73_decision != "TAKE":
        failed.append("PHASE73_NOT_TAKE")
    if not ctx.data_healthy:
        failed.append("PASS_DATA_UNHEALTHY")
    if not ctx.bridge_connected:
        failed.append("EXECUTION_BRIDGE_DISCONNECTED")
    if not ctx.bridge_authenticated:
        failed.append("EXECUTION_NOT_AUTHENTICATED")
    if not ctx.account_verified or not cfg.expected_account:
        failed.append("REJECT_ACCOUNT_NOT_ALLOWED")
    if cfg.expected_account and ctx.connected_account and ctx.connected_account != cfg.expected_account:
        failed.append("REJECT_ACCOUNT_NOT_ALLOWED")
    if not ctx.contract_verified or not _instrument_allowed(cfg, ctx.contract_name or cfg.expected_contract):
        failed.append("REJECT_CONTRACT_MISMATCH")
    if ctx.quantity < 1 or ctx.quantity > cfg.max_quantity:
        failed.append("REJECT_MAX_QUANTITY")
    if ctx.command_duplicate:
        failed.append("DUPLICATE_COMMAND")
    if ctx.signal_duplicate:
        failed.append("DUPLICATE_SIGNAL")
    if ctx.signal_stale:
        failed.append("PASS_STALE_SIGNAL")
    if not ctx.position_reconciled or not ctx.startup_reconciled:
        failed.append("RECONCILIATION_REQUIRED")
    if not ctx.orders_reconciled:
        failed.append("RECONCILIATION_REQUIRED")
    if ctx.unresolved_reconciliation:
        failed.append("RECONCILIATION_REQUIRED")
    if ctx.kill.state is not KillState.EXECUTION_ENABLED:
        failed.append("KILL_SWITCH")
    if ctx.unresolved_halt or ctx.kill.state is KillState.EXECUTION_HALTED:
        failed.append("EXECUTION_HALTED")
    if ctx.open_strategy_positions >= cfg.max_open_strategy_positions:
        failed.append("REJECT_POSITION_OPEN")
    if ctx.existing_side not in {"", "FLAT"} and ctx.intended_side and ctx.existing_side != ctx.intended_side:
        failed.append("REJECT_NO_AUTO_REVERSE")
    if ctx.existing_side not in {"", "FLAT"}:
        failed.append("REJECT_POSITION_OPEN")

    if cfg.execution_mode == "FUNDED":
        if not cfg.funded_account_verified:
            failed.append("FUNDED_ACCOUNT_NOT_VERIFIED")
        if not cfg.allowed_funded_account:
            failed.append("FUNDED_ACCOUNT_NOT_ALLOWLISTED")
        if cfg.allowed_funded_account and ctx.connected_account != cfg.allowed_funded_account:
            failed.append("REJECT_ACCOUNT_NOT_ALLOWED")
        if cfg.allowed_funded_account and cfg.expected_account != cfg.allowed_funded_account:
            failed.append("REJECT_ACCOUNT_NOT_ALLOWED")
        if not ctx.sim_gate_pass:
            failed.append("SIM_GATE_NOT_PASS")
        if cfg.max_quantity != 1 or ctx.quantity != 1:
            failed.append("REJECT_MAX_QUANTITY")

    if ctx.extra_failed:
        failed.append(ctx.extra_failed)

    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for item in failed:
        if item not in seen:
            seen.add(item)
            uniq.append(item)
    if uniq:
        return GateResult(False, uniq[0], uniq)
    return GateResult.ok()


def shadow_would_enter(ctx: GateContext) -> bool:
    """SHADOW records intent without NT routing. Still requires TAKE + healthy data."""
    return (
        ctx.cfg.execution_mode == "SHADOW"
        and ctx.phase73_decision == "TAKE"
        and ctx.data_healthy
        and not ctx.signal_stale
        and not ctx.signal_duplicate
    )


def blocks_new_entries(state: ExecutionState) -> bool:
    return state in {
        ExecutionState.ENTRY_PENDING,
        ExecutionState.ENTRY_ACCEPTED,
        ExecutionState.PARTIALLY_FILLED,
        ExecutionState.FILLED_UNPROTECTED,
        ExecutionState.PROTECTION_PENDING,
        ExecutionState.POSITION_PROTECTED,
        ExecutionState.EXIT_PENDING,
        ExecutionState.FLATTENING,
        ExecutionState.PROTECTION_FAILURE,
        ExecutionState.RECONCILIATION_REQUIRED,
        ExecutionState.HALTED,
    }
