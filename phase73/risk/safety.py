"""Safety controls."""
from __future__ import annotations

from dataclasses import dataclass

from phase73.config.loader import Phase73Config
from phase73.trader.fsm import TraderAction


@dataclass
class SafetyStatus:
    trading_allowed: bool
    reason: str = ""


class SafetyLayer:
    def __init__(self, cfg: Phase73Config) -> None:
        self.cfg = cfg
        self.consecutive_errors = 0
        self.kill_switch = bool(cfg.section("safety").get("kill_switch", False))

    def check_new_entry(self) -> SafetyStatus:
        if self.kill_switch or self.cfg.section("safety").get("emergency_flatten"):
            return SafetyStatus(False, "kill_switch")
        if not self.cfg.trading_enabled:
            return SafetyStatus(False, "trading_disabled")
        if not self.cfg.paper_mode:
            return SafetyStatus(False, "paper_mode_required_in_phase73")
        max_err = int(self.cfg.section("safety").get("max_consecutive_errors", 5))
        if self.consecutive_errors >= max_err:
            return SafetyStatus(False, "max_consecutive_errors")
        return SafetyStatus(True)

    def record_error(self) -> None:
        self.consecutive_errors += 1

    def record_success(self) -> None:
        self.consecutive_errors = 0

    def halt_action(self) -> TraderAction:
        return TraderAction.HALT_NEW_ENTRIES
