"""Original 2.5R trail, plus a breakeven scratch before the trade proves itself."""
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
        self.breakeven_armed = False
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

        proved = self._favorable(mgmt, bar) >= self.cfg.bank_trigger_r * risk
        if not self.banked and not proved:
            if self.breakeven_armed and self._close_through_entry(mgmt, bar):
                return ExitDecision(TraderAction.EXIT_PROFIT, "BREAKEVEN", mgmt.entry_price)
            if self._close_in_profit(mgmt, bar):
                self.breakeven_armed = True
            return None

        self.breakeven_armed = False
        return self._trail(mgmt, bar)

    def _trail(self, mgmt: ManagementState, bar: Bar) -> ExitDecision | None:
        risk = mgmt.risk
        trigger = self.cfg.bank_trigger_r * risk
        lock = self.cfg.lock_stop_r * risk
        trail_dist = self.cfg.trail_atr * mgmt.signal_atr
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

    def _favorable(self, mgmt: ManagementState, bar: Bar) -> float:
        if mgmt.side == "LONG":
            return bar.high - mgmt.entry_price
        return mgmt.entry_price - bar.low

    def _close_in_profit(self, mgmt: ManagementState, bar: Bar) -> bool:
        if mgmt.side == "LONG":
            return bar.close > mgmt.entry_price
        return bar.close < mgmt.entry_price

    def _close_through_entry(self, mgmt: ManagementState, bar: Bar) -> bool:
        if mgmt.side == "LONG":
            return bar.close < mgmt.entry_price
        return bar.close > mgmt.entry_price
