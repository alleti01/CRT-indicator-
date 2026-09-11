"""1-contract bank at 2.5R then trail (suppresses M0_TARGET flatten)."""
from __future__ import annotations

from dataclasses import dataclass

from phase73.market_data.bar import Bar
from phase73.trader.fsm import TraderAction
from phase73.trader.management import ExitDecision, ManagementState, update_excursion


@dataclass(frozen=True)
class TrailOverlayConfig:
    bank_trigger_r: float = 2.5
    lock_stop_r: float = 2.0
    trail_atr: float = 1.0

    @classmethod
    def from_dict(cls, raw: dict) -> TrailOverlayConfig:
        return cls(
            bank_trigger_r=float(raw.get("bank_trigger_r", 2.5)),
            lock_stop_r=float(raw.get("lock_stop_r", 2.0)),
            trail_atr=float(raw.get("trail_atr", 1.0)),
        )


class TrailOverlay:
    def __init__(self, cfg: TrailOverlayConfig | None = None) -> None:
        self.cfg = cfg or TrailOverlayConfig()
        self.banked = False
        self.extreme: float | None = None

    def hide_m0_target(self, mgmt: ManagementState) -> None:
        """Push M0 target out of reach so evaluate_exit never flattens at 2.5R."""
        sign = 1.0 if mgmt.side == "LONG" else -1.0
        mgmt.target_price = mgmt.entry_price + sign * 100.0 * max(mgmt.risk, 1e-9)

    def on_bar(self, mgmt: ManagementState, bar: Bar) -> ExitDecision | None:
        update_excursion(mgmt, bar)
        risk = mgmt.risk
        if risk <= 0:
            return None
        atr = mgmt.signal_atr
        trigger = self.cfg.bank_trigger_r * risk
        lock = self.cfg.lock_stop_r * risk
        trail_dist = self.cfg.trail_atr * atr

        if mgmt.side == "LONG":
            tagged = bar.high >= mgmt.entry_price + trigger
            self.extreme = bar.high if self.extreme is None else max(self.extreme, bar.high)
            if tagged and not self.banked:
                self.banked = True
                mgmt.stop_price = mgmt.entry_price + lock
            if self.banked:
                mgmt.stop_price = max(mgmt.stop_price, self.extreme - trail_dist)
                if bar.low <= mgmt.stop_price:
                    return ExitDecision(TraderAction.EXIT_PROFIT, "TRAIL_STOP", mgmt.stop_price)
        else:
            tagged = bar.low <= mgmt.entry_price - trigger
            self.extreme = bar.low if self.extreme is None else min(self.extreme, bar.low)
            if tagged and not self.banked:
                self.banked = True
                mgmt.stop_price = mgmt.entry_price - lock
            if self.banked:
                mgmt.stop_price = min(mgmt.stop_price, self.extreme + trail_dist)
                if bar.high >= mgmt.stop_price:
                    return ExitDecision(TraderAction.EXIT_PROFIT, "TRAIL_STOP", mgmt.stop_price)
        return None
