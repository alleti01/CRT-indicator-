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
    profit_cap_points: float = 0.0
    profit_cap_r: float = 0.0
    reversal_trail_points: float = 10.0

    @classmethod
    def from_dict(cls, raw: dict) -> TrailOverlayConfig:
        dollars = raw.get("profit_cap_dollars")
        points = raw.get("profit_cap_points", 0.0)
        if dollars is not None:
            points = float(dollars) / float(raw.get("point_value", 20.0))
        return cls(
            bank_trigger_r=float(raw.get("bank_trigger_r", 2.5)),
            lock_stop_r=float(raw.get("lock_stop_r", 2.0)),
            trail_atr=float(raw.get("trail_atr", 1.0)),
            profit_cap_points=float(points or 0.0),
            profit_cap_r=float(raw.get("profit_cap_r", 0.0) or 0.0),
            reversal_trail_points=float(raw.get("reversal_trail_points", 10.0)),
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
        cap = self.cfg.profit_cap_r * risk if self.cfg.profit_cap_r > 0 else self.cfg.profit_cap_points
        if cap > 0:
            return self._cap_or_reversal(mgmt, bar, cap)

        return self._trail(mgmt, bar)

    def _cap_or_reversal(self, mgmt: ManagementState, bar: Bar, cap: float) -> ExitDecision | None:
        trail = self.cfg.reversal_trail_points
        if mgmt.side == "LONG" and bar.high >= mgmt.entry_price + cap:
            return ExitDecision(TraderAction.EXIT_PROFIT, "PROFIT_CAP", mgmt.entry_price + cap)
        if mgmt.side == "SHORT" and bar.low <= mgmt.entry_price - cap:
            return ExitDecision(TraderAction.EXIT_PROFIT, "PROFIT_CAP", mgmt.entry_price - cap)
        if self.extreme is not None:
            if mgmt.side == "LONG" and bar.low <= self.extreme - trail:
                return ExitDecision(TraderAction.EXIT_PROFIT, "REVERSAL", self.extreme - trail)
            if mgmt.side == "SHORT" and bar.high >= self.extreme + trail:
                return ExitDecision(TraderAction.EXIT_PROFIT, "REVERSAL", self.extreme + trail)
        favorable = (bar.high - mgmt.entry_price) if mgmt.side == "LONG" else (mgmt.entry_price - bar.low)
        if favorable < mgmt.risk:
            return None
        price = bar.high if mgmt.side == "LONG" else bar.low
        if self.extreme is None:
            self.extreme = price
        elif mgmt.side == "LONG":
            self.extreme = max(self.extreme, price)
        else:
            self.extreme = min(self.extreme, price)
        return None

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
