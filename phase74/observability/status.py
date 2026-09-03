"""Live system status output."""
from __future__ import annotations

from typing import Any


def build_status(stack: Any) -> dict[str, Any]:
    md = stack.market_data
    eng = stack.engine
    broker = stack.broker
    bar = md.latest_bar()
    health = md.health()
    pos = eng.book.internal
    mgmt = eng.mgmt
    return {
        "SYSTEM": {
            "data_status": getattr(md, "connection_state", health.state.value),
            "webhook_status": stack.webhook_status,
            "broker_status": broker.health().value,
            "paper_mode": stack.cfg.paper_mode,
            "trading_enabled": stack.cfg.trading_enabled,
            "shadow_mode": stack.cfg.shadow_mode,
        },
        "MARKET": {
            "symbol": stack.cfg.symbol,
            "last_bar": bar.timestamp.isoformat() if bar else None,
            "last_price": bar.close if bar else None,
            "atr": md.atr() if bar else None,
            "data_latency_ms": getattr(md, "last_lifecycle", None) and md.last_lifecycle.data_latency_ms,
        },
        "TRADER": {
            "state": eng.state.value,
            "last_signal": eng.pending_signal.signal_id if eng.pending_signal else "",
            "position": pos.side,
            "entry": pos.entry_price,
            "stop": pos.stop_price,
            "target": pos.target_price,
            "current_R": mgmt.current_r if mgmt else None,
            "MFE": mgmt.mfe_r if mgmt else None,
            "MAE": mgmt.mae_r if mgmt else None,
            "minutes_in_trade": pos.minutes_in_trade,
        },
        "EXECUTION": {
            "last_order": broker.open_orders[-1].order_id if broker.open_orders else "",
            "broker_position": broker.get_position().side,
            "pending_orders": len(broker.get_open_orders()),
            "protective_orders": stack.cfg.section("broker").get("protective_orders"),
        },
        "SAFETY": {
            "daily_pnl": stack.daily.daily_pnl,
            "daily_loss_remaining": stack.daily.loss_remaining,
            "kill_switch": stack.cfg.kill_switch,
            "halted": stack.daily.halted,
            "consecutive_errors": stack.daily.consecutive_errors,
        },
    }
