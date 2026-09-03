"""Emergency flatten command."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EmergencyFlattenResult:
    ok: bool
    already_flat: bool
    orders_canceled: int
    reason: str


def emergency_flatten(stack: Any) -> EmergencyFlattenResult:
    """Idempotent flatten — safe to run twice."""
    broker = stack.broker
    engine = stack.engine
    if engine.book.internal.side == "FLAT" and broker.get_position().side == "FLAT":
        engine.state = engine.state.__class__.HALTED if hasattr(engine.state, "HALTED") else engine.state
        return EmergencyFlattenResult(True, True, 0, "ALREADY_FLAT")

    canceled = len(broker.get_open_orders())
    for o in broker.get_open_orders():
        broker.cancel_order(o.order_id)

    bar = stack.market_data.latest_bar()
    if bar and engine.mgmt:
        from phase73.execution.orders import Order, OrderSide

        side = OrderSide.SELL if engine.mgmt.side == "LONG" else OrderSide.BUY
        order = Order.new("FLATTEN", side, 1, stack.cfg.symbol)
        broker.flatten(order, bar.close)
        engine.flatten_emergency()

    stack.daily.halted = True
    stack.cfg.raw.setdefault("mode", {})["trading_enabled"] = False
    return EmergencyFlattenResult(True, False, canceled, "EMERGENCY_FLATTEN")
