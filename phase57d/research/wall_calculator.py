"""Wall family calculators — causal, point-in-time only."""

from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np
import pandas as pd

from phase57d.config import METHOD_VERSION, WALL_TOP_N
from phase57d.research.expiration import StandardExpirationCalendar
from phase57d.research.interfaces import OptionsSnapshot, WallCalculator, WallSnapshot


def _wall_id(
    mapping: str,
    family: str,
    strike: float,
    bucket: str,
    snapshot_id: str,
) -> str:
    raw = f"{mapping}|{family}|{strike:.4f}|{bucket}|{snapshot_id}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _filter_chain(
    chain: pd.DataFrame,
    call_put: Optional[str],
    expiration_scope: str,
    as_of: pd.Timestamp,
    cal: StandardExpirationCalendar,
) -> pd.DataFrame:
    df = chain.copy()
    if call_put is not None:
        df = df[df["call_put"].str.upper() == call_put.upper()]
    if df.empty:
        return df
    df = df.assign(
        dte=df["expiration"].apply(lambda e: cal.dte(as_of, pd.Timestamp(e)))
    )
    if expiration_scope in cal.valid_aggregates():
        df = df[df["dte"].apply(lambda d: cal.in_aggregate(d, expiration_scope))]
    else:
        lo, hi = {"0DTE": (0, 0), "1DTE": (1, 1)}.get(
            expiration_scope, (0, 60)
        )
        df = df[(df["dte"] >= lo) & (df["dte"] <= hi)]
    return df


def _rank_walls(
    snapshot: OptionsSnapshot,
    family: str,
    strikes: pd.Series,
    values: pd.Series,
    buckets: pd.Series,
    atr: float,
    expiration_scope: str,
) -> list[WallSnapshot]:
    if strikes.empty:
        return []
    order = values.rank(ascending=False, method="first").astype(int)
    pctile = values.rank(pct=True) * 100.0
    top = values.nlargest(WALL_TOP_N).index
    walls: list[WallSnapshot] = []
    for idx in top:
        strike = float(strikes.loc[idx])
        val = float(values.loc[idx])
        bucket = str(buckets.loc[idx])
        rank = int(order.loc[idx])
        walls.append(
            WallSnapshot(
                timestamp=snapshot.timestamp,
                underlying=snapshot.underlying,
                mapping=snapshot.mapping,
                wall_family=family,
                wall_id=_wall_id(
                    snapshot.mapping, family, strike, bucket, snapshot.snapshot_id
                ),
                strike=strike,
                wall_value=val,
                wall_rank=rank,
                wall_strength_percentile=float(pctile.loc[idx]),
                expiration_bucket=bucket,
                spot=float(snapshot.spot),
                distance_from_spot=abs(strike - snapshot.spot),
                distance_atr=abs(strike - snapshot.spot) / max(atr, 1e-9),
                source_snapshot_timestamp=snapshot.known_at,
                valid_from=snapshot.known_at,
                valid_until=None,
                method_version=METHOD_VERSION,
            )
        )
    return walls


class OIWallCalculator(WallCalculator):
    """WALL E — concentrated open-interest strike."""

    def __init__(self, side: Optional[str] = None):
        self._side = side  # None = both, "CALL", "PUT"

    def family(self) -> str:
        if self._side == "CALL":
            return "CALL_WALL"
        if self._side == "PUT":
            return "PUT_WALL"
        return "OI_WALL"

    def compute(
        self,
        snapshot: OptionsSnapshot,
        atr: float,
        expiration_scope: str,
    ) -> list[WallSnapshot]:
        cal = StandardExpirationCalendar()
        side = self._side if self._side else None
        df = _filter_chain(snapshot.chain, side, expiration_scope, snapshot.timestamp, cal)
        if df.empty or "oi" not in df.columns:
            return []
        agg = df.groupby(["strike", "expiration"], as_index=False).agg(
            oi=("oi", "sum"),
            call_put=("call_put", "first"),
        )
        agg["bucket"] = agg["expiration"].apply(
            lambda e: cal.bucket(cal.dte(snapshot.timestamp, pd.Timestamp(e)))
        )
        by_strike = agg.groupby("strike").agg(
            oi=("oi", "sum"),
            bucket=("bucket", lambda x: x.mode().iloc[0] if len(x) else ""),
        )
        return _rank_walls(
            snapshot,
            self.family(),
            by_strike.index.to_series(),
            by_strike["oi"],
            by_strike["bucket"],
            atr,
            expiration_scope,
        )


class GammaWallCalculator(WallCalculator):
    """WALL C — estimated gamma exposure concentration.

    Sign assumption: dealer short options → GEX = -gamma * OI * multiplier * spot^2.
    Documented as ASSUMPTION, not proven dealer positioning.
    """

    DEALER_SIGN = -1.0  # short gamma assumption

    def family(self) -> str:
        return "GAMMA_WALL"

    def compute(
        self,
        snapshot: OptionsSnapshot,
        atr: float,
        expiration_scope: str,
    ) -> list[WallSnapshot]:
        cal = StandardExpirationCalendar()
        df = _filter_chain(snapshot.chain, None, expiration_scope, snapshot.timestamp, cal)
        if df.empty or "gamma" not in df.columns or "oi" not in df.columns:
            return []
        spot = float(snapshot.spot)
        mult = df["multiplier"].fillna(100).astype(float)
        gex = (
            self.DEALER_SIGN
            * df["gamma"].astype(float)
            * df["oi"].astype(float)
            * mult
            * spot
            * spot
            * 0.01
        )
        df = df.assign(gex=gex.abs(), bucket=df["expiration"].apply(
            lambda e: cal.bucket(cal.dte(snapshot.timestamp, pd.Timestamp(e)))
        ))
        by_strike = df.groupby("strike").agg(
            gex=("gex", "sum"),
            bucket=("bucket", lambda x: x.mode().iloc[0] if len(x) else ""),
        )
        return _rank_walls(
            snapshot,
            self.family(),
            by_strike.index.to_series(),
            by_strike["gex"],
            by_strike["bucket"],
            atr,
            expiration_scope,
        )


class IVWallCalculator(WallCalculator):
    """WALL D — IV-derived concentration (requires IV snapshots)."""

    def family(self) -> str:
        return "IV_WALL"

    def compute(
        self,
        snapshot: OptionsSnapshot,
        atr: float,
        expiration_scope: str,
    ) -> list[WallSnapshot]:
        cal = StandardExpirationCalendar()
        df = _filter_chain(snapshot.chain, None, expiration_scope, snapshot.timestamp, cal)
        if df.empty or "iv" not in df.columns:
            return []
        df = df.assign(
            iv_notional=df["iv"].astype(float) * df["oi"].astype(float),
            bucket=df["expiration"].apply(
                lambda e: cal.bucket(cal.dte(snapshot.timestamp, pd.Timestamp(e)))
            ),
        )
        by_strike = df.groupby("strike").agg(
            iv_notional=("iv_notional", "sum"),
            bucket=("bucket", lambda x: x.mode().iloc[0] if len(x) else ""),
        )
        return _rank_walls(
            snapshot,
            self.family(),
            by_strike.index.to_series(),
            by_strike["iv_notional"],
            by_strike["bucket"],
            atr,
            expiration_scope,
        )


def all_calculators() -> list[WallCalculator]:
    return [
        OIWallCalculator("CALL"),
        OIWallCalculator("PUT"),
        OIWallCalculator(None),
        GammaWallCalculator(),
        IVWallCalculator(),
    ]
