"""Load 1M market data for Phase84."""
from __future__ import annotations

import pandas as pd


def load_m1() -> pd.DataFrame:
    from phase45.execution.data_1m import load_market_1m

    m1 = load_market_1m()
    if m1.index.tz is None:
        m1 = m1.tz_localize("America/Chicago")
    m1 = m1.tz_convert("UTC")
    return m1
