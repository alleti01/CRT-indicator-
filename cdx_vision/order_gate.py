"""Decide whether a finished chart read is complete enough to allow an order.

The vision job never places the order. The live stack asks this after the read.
"""
from __future__ import annotations

from decimal import Decimal

from cdx_vision.models import VisionResult

TICK = Decimal("0.25")


def _on_tick(price: Decimal) -> bool:
    units = price / TICK
    return units == units.to_integral_value()


def _geometry(direction: str, entry: Decimal, stop: Decimal, tp1: Decimal, tp2: Decimal) -> bool:
    if direction == "SHORT":
        return stop > entry > tp1 > tp2
    if direction == "LONG":
        return stop < entry < tp1 < tp2
    return False


def levels_allow_order(result: VisionResult) -> tuple[bool, str]:
    """True only when Entry, SL, TP1, and TP2 were pulled from the chart."""
    if not result.confirmed:
        return False, "VISION_NOT_CONFIRMED"
    entry = result.native_entry or result.entry
    stop = result.stop
    tp1 = result.tp1
    tp2 = result.tp2
    if entry is None or stop is None or tp1 is None or tp2 is None:
        return False, "MISSING_LEVEL"
    if not all(_on_tick(price) for price in (entry, stop, tp1, tp2)):
        return False, "OFF_TICK"
    if not _geometry(result.direction, entry, stop, tp1, tp2):
        return False, "BAD_GEOMETRY"
    if not (result.initial_levels_visible or result.auto_right_success):
        return False, "LEVELS_NOT_ON_SCREEN"
    if "VISION_AUTO_RIGHT_NO_MOVEMENT" in result.reasons:
        return False, "NO_MOVEMENT"
    return True, "LEVELS_PULLED"
