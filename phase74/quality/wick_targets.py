"""CDX signals-only targets: unswept 3-minute wicks, stop mirrors the first."""
from __future__ import annotations

from datetime import datetime

from phase73.market_data.bar import Bar

CLUSTER_POINTS = 3.0


def _to_3m(bars: list[Bar]) -> list[tuple[datetime, float, float, float]]:
    groups: dict[int, list[Bar]] = {}
    for bar in bars:
        epoch = int(bar.timestamp.timestamp())
        groups.setdefault(epoch - epoch % 180, []).append(bar)
    out: list[tuple[datetime, float, float, float]] = []
    for key in sorted(groups):
        group = groups[key]
        out.append(
            (
                group[0].timestamp,
                max(bar.high for bar in group),
                min(bar.low for bar in group),
                group[-1].close,
            )
        )
    return out


def wick_targets(
    side: str,
    entry: float,
    bars: list[Bar],
    asof: datetime,
    *,
    cluster: float = CLUSTER_POINTS,
) -> tuple[float, float | None] | None:
    """Return (first target, second target) from untouched swing wicks.

    The first target is the far wick of the nearest cluster. The stop is the
    same distance on the other side of the entry.
    """
    series = _to_3m([bar for bar in bars if bar.timestamp <= asof])
    n = len(series)
    left, right = 2, 1
    hits: list[float] = []
    for i in range(left, n - right):
        if series[i + right][0] > asof:
            break
        if side == "LONG":
            level = series[i][1]
            if level <= entry:
                continue
            if any(series[i - k][1] >= level for k in range(1, left + 1)):
                continue
            if any(series[i + k][1] >= level for k in range(1, right + 1)):
                continue
            if any(series[j][1] >= level for j in range(i + 1, n) if series[j][0] <= asof):
                continue
        else:
            level = series[i][2]
            if level >= entry:
                continue
            if any(series[i - k][2] <= level for k in range(1, left + 1)):
                continue
            if any(series[i + k][2] <= level for k in range(1, right + 1)):
                continue
            if any(series[j][2] <= level for j in range(i + 1, n) if series[j][0] <= asof):
                continue
        hits.append(level)
    if not hits:
        return None
    hits = sorted(hits) if side == "LONG" else sorted(hits, reverse=True)
    bunch = [hits[0]]
    for level in hits[1:]:
        if abs(level - bunch[-1]) <= cluster:
            bunch.append(level)
        else:
            break
    first = max(bunch) if side == "LONG" else min(bunch)
    rest = [level for level in hits if level > first + cluster] if side == "LONG" else [
        level for level in hits if level < first - cluster
    ]
    second = None
    if rest:
        bunch2 = [rest[0]]
        for level in rest[1:]:
            if abs(level - bunch2[-1]) <= cluster:
                bunch2.append(level)
            else:
                break
        second = max(bunch2) if side == "LONG" else min(bunch2)
    return first, second
