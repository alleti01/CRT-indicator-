"""Two-stage exit: scratch small trades, then let a proved runner trail wide."""
from __future__ import annotations

from dataclasses import dataclass

from phase73.market_data.bar import Bar
from phase73.trader.fsm import TraderAction
from phase73.trader.management import ExitDecision, ManagementState, update_excursion


@dataclass(frozen=True)
class TrailOverlayConfig:
    bank_trigger_r: float = 2.5
    runner_trigger_r: float = 4.0
    trail_atr: float = 2.0
    # Kept so older configs still load. The +2R lock is no longer applied.
    lock_stop_r: float = 2.0

    @classmethod
    def from_dict(cls, raw: dict) -> TrailOverlayConfig:
        return cls(
            bank_trigger_r=float(raw.get("bank_trigger_r", 2.5)),
            runner_trigger_r=float(raw.get("runner_trigger_r", 4.0)),
            trail_atr=float(raw.get("trail_atr", 2.0)),
            lock_stop_r=float(raw.get("lock_stop_r", 2.0)),
        )


class TrailOverlay:
    def __init__(self, cfg: TrailOverlayConfig | None = None) -> None:
        self.cfg = cfg or TrailOverlayConfig()
        self.banked = False
        self.breakeven_armed = False
        self.trailing = False
        self.extreme: float | None = None
        self.active_trail_stop: float | None = None
        self.original_stop: float | None = None

    def hide_m0_target(self, mgmt: ManagementState) -> None:
        """Push M0 target out of reach so evaluate_exit never flattens at 2.5R."""
        sign = 1.0 if mgmt.side == "LONG" else -1.0
        mgmt.target_price = mgmt.entry_price + sign * 100.0 * max(mgmt.risk, 1e-9)

    def on_bar(self, mgmt: ManagementState, bar: Bar) -> ExitDecision | None:
        update_excursion(mgmt, bar)
        risk = mgmt.risk
        if risk <= 0:
            return None
        if self.original_stop is None:
            self.original_stop = mgmt.stop_price

        if self.trailing and self.active_trail_stop is not None and self._trail_hit(mgmt, bar):
            return ExitDecision(TraderAction.EXIT_PROFIT, "TRAIL_STOP", self.active_trail_stop)

        if not self.banked and self._reached(mgmt, bar, self.cfg.bank_trigger_r):
            self.banked = True
            self.breakeven_armed = False
            mgmt.stop_price = self.original_stop

        if self.breakeven_armed and not self.banked and self._close_through_entry(mgmt, bar):
            return ExitDecision(TraderAction.EXIT_PROFIT, "BREAKEVEN", mgmt.entry_price)

        if not self.banked:
            if self._close_in_profit(mgmt, bar):
                self.breakeven_armed = True
            return None

        if self.trailing or self._reached(mgmt, bar, self.cfg.runner_trigger_r):
            self._advance_trail(mgmt, bar)
        return None

    def _reached(self, mgmt: ManagementState, bar: Bar, r_multiple: float) -> bool:
        return self._favorable(mgmt, bar) >= r_multiple * mgmt.risk

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

    def _trail_hit(self, mgmt: ManagementState, bar: Bar) -> bool:
        stop = self.active_trail_stop
        if stop is None:
            return False
        if mgmt.side == "LONG":
            return bar.low <= stop
        return bar.high >= stop

    def _advance_trail(self, mgmt: ManagementState, bar: Bar) -> None:
        self.trailing = True
        favorable_price = bar.high if mgmt.side == "LONG" else bar.low
        if self.extreme is None:
            self.extreme = favorable_price
        elif mgmt.side == "LONG":
            self.extreme = max(self.extreme, favorable_price)
        else:
            self.extreme = min(self.extreme, favorable_price)
        dist = self.cfg.trail_atr * mgmt.signal_atr
        candidate = self.extreme - dist if mgmt.side == "LONG" else self.extreme + dist
        if self.active_trail_stop is None:
            self.active_trail_stop = candidate
        elif mgmt.side == "LONG":
            self.active_trail_stop = max(self.active_trail_stop, candidate)
        else:
            self.active_trail_stop = min(self.active_trail_stop, candidate)
        # The new stop is for later bars. This bar already passed the hit check.
        mgmt.stop_price = self.original_stop if self.original_stop is not None else mgmt.stop_price
