"""Place the protective stop on the price read from the chart."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def chart_stop_for_fill(
    side: str,
    fill: float,
    visual_stop: float,
    tick: float = 0.25,
) -> tuple[float, float] | None:
    """Return (stop price, risk points) when the chart stop is still beyond the fill."""
    step = Decimal(str(tick if tick > 0 else 0.25))
    stop = (Decimal(str(visual_stop)) / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step
    stop_f = float(stop)
    side_name = (side or "").upper()
    if side_name == "LONG" and stop_f >= fill:
        return None
    if side_name == "SHORT" and stop_f <= fill:
        return None
    if side_name not in {"LONG", "SHORT"}:
        return None
    risk = abs(fill - stop_f)
    if risk <= 0:
        return None
    return stop_f, risk
