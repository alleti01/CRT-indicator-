"""Causal 2-minute bars from 1-minute OHLC. Clock-aligned on NY time."""
from __future__ import annotations

import numpy as np
import pandas as pd

from phase83.python.config import NY_TZ, VOL_LOOKBACK_2M


def build_2m(arr: dict) -> dict:
    """
    A 2M bucket is floor(NY minute-of-day / 2).
    Completes only when the bucket contains two 1M bars.
    Entry is the next 1M open after the last 1M bar of the completed 2M.
    """
    ny = pd.DatetimeIndex(arr["ny"])
    n = arr["n"]
    minute = ny.hour * 60 + ny.minute
    bucket = (ny.normalize().view("i8") // 10**9) * 10_000 + (minute // 2)

    complete = np.zeros(n, dtype=bool)
    o2 = np.full(n, np.nan)
    h2 = np.full(n, np.nan)
    l2 = np.full(n, np.nan)
    c2 = np.full(n, np.nan)
    v2 = np.full(n, np.nan)
    n_in = np.zeros(n, dtype=np.int16)

    i = 0
    while i < n:
        b = bucket[i]
        j = i + 1
        while j < n and bucket[j] == b:
            j += 1
        # [i, j)
        cnt = j - i
        last = j - 1
        n_in[last] = cnt
        if cnt >= 2:
            complete[last] = True
            o2[last] = arr["op"][i]
            h2[last] = arr["hi"][i:j].max()
            l2[last] = arr["lo"][i:j].min()
            c2[last] = arr["cl"][last]
            v2[last] = arr["vol"][i:j].sum()
        i = j

    # causal rolling median of prior completed 2M volumes
    vol_base = np.full(n, np.nan)
    hist: list[float] = []
    for k in range(n):
        if complete[k]:
            if hist:
                vol_base[k] = float(np.median(hist[-VOL_LOOKBACK_2M:]))
            hist.append(float(v2[k]))

    return {
        "complete": complete,
        "open": o2,
        "high": h2,
        "low": l2,
        "close": c2,
        "volume": v2,
        "vol_base": vol_base,
        "n_in": n_in,
    }
