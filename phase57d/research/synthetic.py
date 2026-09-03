"""Synthetic options snapshots for framework/unit testing only.

NOT for performance research — used to validate causal engine logic.
"""

from __future__ import annotations

import hashlib
from typing import Iterator

import numpy as np
import pandas as pd

from phase57d.research.interfaces import OptionsSnapshot
from phase57d.research.schema import OPTIONS_CHAIN_COLUMNS


def make_synthetic_chain(
    spot: float,
    ts: pd.Timestamp,
    strikes: list[float] | None = None,
) -> pd.DataFrame:
    """Generate a minimal causal options chain for engine tests."""
    if strikes is None:
        strikes = [spot - 50, spot - 25, spot, spot + 25, spot + 50]
    rows = []
    exp = (ts + pd.Timedelta(days=2)).normalize()
    for strike in strikes:
        for cp in ("CALL", "PUT"):
            oi = int(1000 + abs(strike - spot) * 10 + (50 if cp == "CALL" else 0))
            rows.append({
                "option_symbol": f"SYN{strike}{cp[0]}",
                "underlying": "NQ",
                "timestamp": ts,
                "expiration": exp,
                "strike": strike,
                "call_put": cp,
                "bid": 1.0,
                "ask": 1.2,
                "mid": 1.1,
                "last": 1.1,
                "iv": 0.20 + abs(strike - spot) * 0.001,
                "oi": oi,
                "volume": 100,
                "delta": 0.5 if cp == "CALL" else -0.5,
                "gamma": 0.01,
                "vega": 0.1,
                "theta": -0.05,
                "underlying_price": spot,
                "multiplier": 100,
                "snapshot_id": hashlib.sha256(f"{ts}{spot}".encode()).hexdigest()[:8],
                "known_at": ts,
            })
    return pd.DataFrame(rows, columns=OPTIONS_CHAIN_COLUMNS)


def synthetic_snapshots(
    bars: pd.DataFrame,
    every_n: int = 30,
    mapping: str = "MAP_NQ_NDX",
) -> Iterator[OptionsSnapshot]:
    """Emit synthetic snapshots at causal intervals from underlying bars."""
    for i, (ts, bar) in enumerate(bars.iterrows()):
        if i % every_n != 0:
            continue
        spot = float(bar["close"])
        chain = make_synthetic_chain(spot, ts)
        sid = hashlib.sha256(f"{mapping}|{ts.isoformat()}".encode()).hexdigest()[:12]
        yield OptionsSnapshot(
            timestamp=ts,
            underlying="NQ",
            mapping=mapping,
            spot=spot,
            chain=chain,
            known_at=ts,
            snapshot_id=sid,
        )
