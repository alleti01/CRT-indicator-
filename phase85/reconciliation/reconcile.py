"""Compare Python expected state vs NinjaTrader authority. No auto-correct orders."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BrokerSnapshot:
    account: str = ""
    instrument: str = ""
    side: str = "FLAT"
    quantity: int = 0
    entry_price: float | None = None
    working_entry_orders: int = 0
    working_stop: bool = False
    working_target: bool = False
    unexpected_orders: int = 0
    orphan_orders: int = 0
    connected: bool = False


@dataclass
class ExpectedSnapshot:
    side: str = "FLAT"
    quantity: int = 0
    instrument: str = ""
    protection_required: bool = False
    expected_stop: bool = False
    expected_target: bool = False


@dataclass
class ReconciliationResult:
    ok: bool
    reason: str = "OK"
    mismatches: list[str] = field(default_factory=list)
    block_new_entries: bool = False


def reconcile_execution(expected: ExpectedSnapshot, actual: BrokerSnapshot) -> ReconciliationResult:
    mismatches: list[str] = []
    if not actual.connected:
        mismatches.append("BROKER_DISCONNECTED")
    if expected.instrument and actual.instrument and expected.instrument != actual.instrument:
        mismatches.append("INSTRUMENT_MISMATCH")
    exp_side = expected.side or "FLAT"
    act_side = actual.side or "FLAT"
    if exp_side != act_side:
        mismatches.append("DIRECTION_MISMATCH")
    if expected.quantity != actual.quantity:
        mismatches.append("QUANTITY_MISMATCH")
    if expected.protection_required and act_side != "FLAT":
        if expected.expected_stop and not actual.working_stop:
            mismatches.append("MISSING_STOP")
        if expected.expected_target and not actual.working_target:
            mismatches.append("MISSING_TARGET")
    if actual.unexpected_orders:
        mismatches.append("UNEXPECTED_WORKING_ORDERS")
    if actual.orphan_orders:
        mismatches.append("ORPHAN_ORDER")
    if exp_side == "FLAT" and act_side != "FLAT":
        mismatches.append("UNEXPECTED_POSITION")
    if mismatches:
        return ReconciliationResult(False, "RECONCILIATION_REQUIRED", mismatches, True)
    return ReconciliationResult(True, "OK", [], False)
