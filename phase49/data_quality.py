"""Data quality audit for forward runs."""

from __future__ import annotations

import pandas as pd

from phase45.execution.data_1m import load_market_1m

from .data.loaders import load_forward_1m, load_forward_15m, load_market_1m_phase49, load_market_15m_phase49
from .data.quality import audit_phase49_data
from .forward_engine import frozen_cutoff


def audit_data_quality(
    market_15m: pd.DataFrame | None = None,
    market_1m: pd.DataFrame | None = None,
) -> dict:
    m15 = market_15m if market_15m is not None else load_market_15m_phase49()
    m1 = market_1m if market_1m is not None else load_market_1m_phase49()
    fwd_1 = load_forward_1m(ingest=False)
    fwd_15 = load_forward_15m(ingest=False)
    result = audit_phase49_data(m15, m1, forward_1m=fwd_1, forward_15m=fwd_15)
    result["development_cutoff"] = str(frozen_cutoff())
    return result


def audit_research_loader() -> dict:
    """Verify Phase45 default loader does not include forward rows."""
    from .data.firewall import forward_start_ts

    m1 = load_market_1m()
    start = forward_start_ts()
    fwd_rows = int((m1.index >= start).sum()) if not m1.empty else 0
    return {"pass": fwd_rows == 0, "forward_rows_in_research_loader": fwd_rows}
