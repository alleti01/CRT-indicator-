"""NQ underlying adapter — reuses Phase53 data pipeline."""

from __future__ import annotations

import pandas as pd

from phase57d.config import TIMEZONE
from phase57d.research.interfaces import ContractSpec, UnderlyingAdapter


class NQUnderlyingAdapter(UnderlyingAdapter):
    """Adapter for NQ continuous futures OHLC."""

    def contract_spec(self) -> ContractSpec:
        return ContractSpec(
            symbol="NQ",
            tick_size=0.25,
            multiplier=20.0,
            session_open="08:30",
            session_close="15:00",
            timezone=TIMEZONE,
        )

    def load_bars(self, timeframe: str = "1M") -> pd.DataFrame:
        from phase53.research.data import load_markets

        m1, m5, m15 = load_markets()
        if timeframe == "1M":
            return m1
        if timeframe == "5M":
            return m5
        if timeframe == "15M":
            return m15
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    def atr_at(self, ts: pd.Timestamp, bars: pd.DataFrame) -> float:
        if ts in bars.index and "atr" in bars.columns:
            val = bars.loc[ts, "atr"]
            if pd.notna(val) and val > 0:
                return float(val)
        idx = bars.index.searchsorted(ts, side="right") - 1
        idx = max(0, min(idx, len(bars) - 1))
        val = bars.iloc[idx].get("atr", bars.iloc[idx]["high"] - bars.iloc[idx]["low"])
        return float(val) if pd.notna(val) and val > 0 else 1.0
