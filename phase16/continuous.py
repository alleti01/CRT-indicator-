"""Causal continuous-contract construction for individual futures contracts.

The default adjustment is a forward additive splice: when the active contract
rolls, the incoming contract is shifted so its first adjusted open equals the
last adjusted close of the outgoing contract. This prevents the rollover gap
itself from generating a BOS, sweep, or setup and uses no observations after
the roll. It is intentionally different from vendor unadjusted continuous data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

import pandas as pd

from .resample import cme_session_date


PRICE_COLUMNS = ["open", "high", "low", "close"]


def _require_contracts(frame: pd.DataFrame) -> None:
    if "contract" not in frame.columns:
        raise ValueError("individual-contract input must include a contract column")


def select_provider_rolls(
    frame: pd.DataFrame, instrument_column: str = "instrument_id"
) -> pd.DataFrame:
    """Use a provider's continuous-contract instrument transitions as rolls.

    Databento's continuous OHLCV includes the resolved underlying
    ``instrument_id``. This function preserves that provider-selected roll
    schedule while making it available to the same gap-adjustment routine used
    by explicit and volume rolls.
    """
    if instrument_column not in frame.columns:
        raise ValueError(
            f"provider-roll input must include {instrument_column}; "
            "download the continuous data with instrument identifiers"
        )
    result = frame.copy()
    result["contract"] = result[instrument_column].astype(str)
    return result


def select_explicit_rolls(
    frame: pd.DataFrame,
    initial_contract: str,
    rolls: pd.DataFrame,
) -> pd.DataFrame:
    """Select one contract using rows: roll_timestamp,new_contract."""
    _require_contracts(frame)
    required = {"roll_timestamp", "new_contract"}
    if not required.issubset(rolls.columns):
        raise ValueError("roll schedule needs roll_timestamp and new_contract")
    schedule = rolls.copy()
    timestamps = pd.to_datetime(schedule["roll_timestamp"], errors="raise")
    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize(frame.index.tz)
    else:
        timestamps = timestamps.dt.tz_convert(frame.index.tz)
    schedule["roll_timestamp"] = timestamps
    schedule = schedule.sort_values("roll_timestamp")

    active = initial_contract
    starts = [(frame.index.min(), active)]
    starts.extend(
        (row.roll_timestamp, str(row.new_contract)) for row in schedule.itertuples()
    )
    pieces = []
    for number, (start, contract) in enumerate(starts):
        end = starts[number + 1][0] if number + 1 < len(starts) else None
        mask = (frame.index >= start) & (frame["contract"] == contract)
        if end is not None:
            mask &= frame.index < end
        selected = frame.loc[mask].copy()
        if selected.empty:
            raise ValueError(f"no data for active contract {contract} from {start}")
        pieces.append(selected)
    return pd.concat(pieces).sort_index()


def select_volume_rolls(
    frame: pd.DataFrame,
    contract_order: Sequence[str],
    *,
    confirm_sessions: int = 1,
) -> pd.DataFrame:
    """Roll forward after a later contract leads daily volume for N sessions.

    ``contract_order`` must be chronological. The selector never rolls back to
    an earlier expiry. A session's active contract is selected only from volume
    observed through the prior completed session, so the roll builder does not
    use later bars from the session it is constructing.
    """
    _require_contracts(frame)
    if confirm_sessions < 1:
        raise ValueError("confirm_sessions must be >= 1")
    order = {str(contract): position for position, contract in enumerate(contract_order)}
    unknown = set(frame["contract"].astype(str)) - set(order)
    if unknown:
        raise ValueError(f"contract_order is missing: {sorted(unknown)}")
    working = frame.copy()
    working["_session"] = cme_session_date(working.index).to_numpy()
    daily = working.groupby(["_session", "contract"])["volume"].sum().unstack(fill_value=0)
    current_position = 0
    candidate = None
    candidate_count = 0
    active_by_session: Dict[pd.Timestamp, str] = {}
    for session, row in daily.sort_index().iterrows():
        # Freeze today's selection before reading today's completed volume.
        active_by_session[pd.Timestamp(session)] = str(contract_order[current_position])
        eligible = [contract for contract in contract_order if order[contract] >= current_position]
        leader = max(eligible, key=lambda contract: float(row.get(contract, 0.0)))
        leader_position = order[leader]
        if leader_position > current_position:
            if leader == candidate:
                candidate_count += 1
            else:
                candidate = leader
                candidate_count = 1
            if candidate_count >= confirm_sessions:
                current_position = leader_position
                candidate = None
                candidate_count = 0
        else:
            candidate = None
            candidate_count = 0
    active = working["_session"].map(active_by_session)
    selected = working.loc[working["contract"].astype(str).eq(active)].drop(columns="_session")
    if selected.empty:
        raise ValueError("volume roll selection produced no rows")
    return selected.sort_index()


def forward_adjust_rolls(selected: pd.DataFrame) -> pd.DataFrame:
    """Remove contract-transition gaps with a causal additive adjustment."""
    _require_contracts(selected)
    result = selected.sort_index().copy()
    if result.empty:
        return result
    offset = 0.0
    previous_contract = str(result["contract"].iloc[0])
    previous_adjusted_close: Optional[float] = None
    adjusted_rows = []
    for timestamp, row in result.iterrows():
        contract = str(row["contract"])
        if contract != previous_contract and previous_adjusted_close is not None:
            offset = previous_adjusted_close - float(row["open"])
            previous_contract = contract
        adjusted = row.copy()
        for column in PRICE_COLUMNS:
            adjusted[column] = float(row[column]) + offset
        adjusted["roll_adjustment"] = offset
        previous_adjusted_close = float(adjusted["close"])
        adjusted_rows.append(adjusted)
    output = pd.DataFrame(adjusted_rows, index=result.index)
    output.index.name = result.index.name
    return output
