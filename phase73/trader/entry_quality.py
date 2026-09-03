"""Conservative entry quality V1."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from phase73.config.loader import Phase73Config
from phase73.market_data.base import MarketDataProvider
from phase73.market_data.health import DataHealth
from phase73.trader.fsm import TraderAction
from phase73.webhook.schemas import PineSignal


@dataclass
class EntryDecision:
    action: TraderAction
    reason: str
    signal_age_seconds: float = 0.0
    signal_age_bars: float = 0.0
    price_distance: float = 0.0
    price_distance_atr: float = 0.0


def evaluate_entry(
    signal: PineSignal,
    md: MarketDataProvider,
    cfg: Phase73Config,
    *,
    position_side: str,
    now: datetime | None = None,
) -> EntryDecision:
    now = now or md.current_time()
    health = md.health()
    if health.state != DataHealth.DATA_HEALTHY:
        return EntryDecision(TraderAction.PASS_DATA_UNHEALTHY, health.state.value)

    if position_side in ("LONG", "SHORT"):
        return EntryDecision(TraderAction.PASS_POSITION_CONFLICT, "position active")

    age = (now - signal.signal_time_utc).total_seconds()
    if age > cfg.max_signal_age_seconds:
        return EntryDecision(TraderAction.PASS_STALE, f"age={age:.0f}s", signal_age_seconds=age)

    snap = md.snapshot_features(signal.signal_price, signal.signal_time_utc)
    price = snap.get("current_price")
    atr = snap.get("current_atr") or signal.atr
    dist = (price - signal.signal_price) if price is not None else 0.0
    dist_atr = dist / atr if atr else 0.0

    eq = cfg.section("entry_quality")
    if eq.get("pass_late_enabled") and age > eq.get("max_signal_age_seconds", cfg.max_signal_age_seconds):
        return EntryDecision(TraderAction.PASS_LATE, "late", signal_age_seconds=age)

    if eq.get("pass_chase_enabled") and abs(dist_atr) > float(eq.get("max_chase_atr", 1.5)):
        return EntryDecision(TraderAction.PASS_CHASE, f"dist_atr={dist_atr:.2f}", price_distance_atr=dist_atr)

    direction = signal.direction
    action = TraderAction.TAKE_LONG if direction == "LONG" else TraderAction.TAKE_SHORT
    return EntryDecision(
        action,
        "TAKE",
        signal_age_seconds=age,
        price_distance=dist,
        price_distance_atr=dist_atr,
    )
