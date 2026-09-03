"""Data quality checks for forward 1M feed."""

from __future__ import annotations

import pandas as pd

from phase53.research.data import align_htf_to_1m, load_markets
from phase56.config import FORWARD_START_TIMESTAMP_CT, HOLDOUT_END, RESULTS


def check_data_quality() -> pd.DataFrame:
    m1, m5, m15 = load_markets()
    tz = m1.index.tz
    start = pd.Timestamp(FORWARD_START_TIMESTAMP_CT, tz=tz)
    end = pd.Timestamp(HOLDOUT_END, tz=tz)
    fwd = m1.loc[(m1.index >= start) & (m1.index <= end)]
    dup = int(fwd.index.duplicated().sum())
    diffs = fwd.index.to_series().diff()
    gaps = diffs[diffs > pd.Timedelta(minutes=1)]
    m5a = align_htf_to_1m(m1, m5)
    m15a = align_htf_to_1m(m1, m15)
    row = {
        "forward_bars": len(fwd),
        "duplicate_bars": dup,
        "gaps_over_1m": len(gaps),
        "first_bar": str(fwd.index.min()),
        "last_bar": str(fwd.index.max()),
        "timezone": str(fwd.index.tz),
        "m5_aligned_null_pct": float(m5a.loc[fwd.index, "close"].isna().mean()) if len(fwd) else 0,
        "m15_aligned_null_pct": float(m15a.loc[fwd.index, "close"].isna().mean()) if len(fwd) else 0,
        "status": "PASS" if dup == 0 else "FAIL",
    }
    out = pd.DataFrame([row])
    RESULTS.mkdir(parents=True, exist_ok=True)
    out.to_csv(RESULTS / "data_quality.csv", index=False)
    return out
