"""Translate frozen Phase73 M0 from the actual NinjaTrader fill. Do not redesign."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from phase73.config.loader import Phase73Config, load_config
from phase73.trader.management import ManagementState, build_management


@dataclass
class M0Protection:
    side: str
    actual_fill: float
    expected_entry: float | None
    risk: float
    stop_price: float
    target_price: float
    signal_atr: float
    slippage_points: float
    slippage_ticks: float
    reference: str = "phase73.trader.management.build_management"


def m0_from_actual_fill(
    side: str,
    actual_fill: float,
    signal_atr: float,
    entry_time: datetime,
    *,
    expected_entry: float | None = None,
    tick_size: float = 0.25,
    cfg: Phase73Config | None = None,
) -> M0Protection:
    p73 = cfg or load_config()
    mgmt: ManagementState = build_management(side, actual_fill, signal_atr, p73, entry_time)
    expected = expected_entry if expected_entry is not None else actual_fill
    slip_pts = actual_fill - expected
    slip_ticks = slip_pts / tick_size if tick_size else 0.0
    return M0Protection(
        side=side,
        actual_fill=actual_fill,
        expected_entry=expected_entry,
        risk=mgmt.risk,
        stop_price=mgmt.stop_price,
        target_price=mgmt.target_price,
        signal_atr=signal_atr,
        slippage_points=slip_pts,
        slippage_ticks=slip_ticks,
    )
