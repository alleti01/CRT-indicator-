"""M0 baseline trade management."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from phase73.config.loader import Phase73Config
from phase73.market_data.bar import Bar
from phase73.trader.fsm import TraderAction


@dataclass
class ManagementState:
    side: str
    entry_price: float
    stop_price: float
    target_price: float
    risk: float
    entry_time: datetime
    signal_atr: float
    mfe_r: float = 0.0
    mae_r: float = 0.0
    current_r: float = 0.0
    bars_in_trade: int = 0


@dataclass
class ExitDecision:
    action: TraderAction
    reason: str
    exit_price: float | None = None


def build_management(
    side: str,
    entry_price: float,
    signal_atr: float,
    cfg: Phase73Config,
    entry_time: datetime,
) -> ManagementState:
    risk = cfg.stop_atr * signal_atr
    if side == "LONG":
        stop = entry_price - risk
        target = entry_price + cfg.target_r * risk
    else:
        stop = entry_price + risk
        target = entry_price - cfg.target_r * risk
    return ManagementState(
        side=side,
        entry_price=entry_price,
        stop_price=stop,
        target_price=target,
        risk=risk,
        entry_time=entry_time,
        signal_atr=signal_atr,
    )


def update_excursion(mgmt: ManagementState, bar: Bar) -> None:
    if mgmt.risk <= 0:
        return
    if mgmt.side == "LONG":
        fav = (bar.high - mgmt.entry_price) / mgmt.risk
        adv = (mgmt.entry_price - bar.low) / mgmt.risk
        mgmt.current_r = (bar.close - mgmt.entry_price) / mgmt.risk
    else:
        fav = (mgmt.entry_price - bar.low) / mgmt.risk
        adv = (bar.high - mgmt.entry_price) / mgmt.risk
        mgmt.current_r = (mgmt.entry_price - bar.close) / mgmt.risk
    mgmt.mfe_r = max(mgmt.mfe_r, fav)
    mgmt.mae_r = max(mgmt.mae_r, adv)


def evaluate_exit(mgmt: ManagementState, bar: Bar, cfg: Phase73Config, now: datetime) -> ExitDecision | None:
    update_excursion(mgmt, bar)
    mgmt.bars_in_trade += 1
    minutes = (now - mgmt.entry_time).total_seconds() / 60.0

    hit_stop = hit_target = False
    if mgmt.side == "LONG":
        hit_stop = bar.low <= mgmt.stop_price
        hit_target = bar.high >= mgmt.target_price
    else:
        hit_stop = bar.high >= mgmt.stop_price
        hit_target = bar.low <= mgmt.target_price

    if hit_stop and hit_target:
        if cfg.same_bar_collision == "STOP_FIRST":
            return ExitDecision(TraderAction.EXIT_STOP, "SAME_BAR_STOP_FIRST", mgmt.stop_price)
        return ExitDecision(TraderAction.EXIT_PROFIT, "SAME_BAR_TARGET_FIRST", mgmt.target_price)

    if hit_stop:
        return ExitDecision(TraderAction.EXIT_STOP, "M0_STOP", mgmt.stop_price)
    if hit_target:
        return ExitDecision(TraderAction.EXIT_PROFIT, "M0_TARGET", mgmt.target_price)

    if minutes >= cfg.max_hold_minutes:
        return ExitDecision(TraderAction.EXIT_TIME, "MAX_HOLD_60M", bar.close)

    if cfg.enable_time_progress_exit:
        t5_min = int(cfg.section("management").get("time_progress_minutes", 15))
        t5_mfe = float(cfg.section("management").get("time_progress_mfe_r", 1.0))
        if minutes >= t5_min and mgmt.mfe_r < t5_mfe:
            return ExitDecision(TraderAction.EXIT_NO_PROGRESS, "TIME_PROGRESS_15M_LT_1R", bar.close)

    return None
