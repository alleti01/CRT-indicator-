"""Observable auction market states — causal sequential classifier."""
from __future__ import annotations

from enum import Enum

import numpy as np
import pandas as pd

from .config import ACCEPT_MIN_BARS_OUTSIDE, ACCEPT_MIN_CLOSES_OUTSIDE, REJECT_MAX_BARS_OUTSIDE


class AuctionState(str, Enum):
    BALANCED = "BALANCED"
    ROTATIONAL = "ROTATIONAL"
    TESTING_UPPER_VALUE = "TESTING_UPPER_VALUE"
    TESTING_LOWER_VALUE = "TESTING_LOWER_VALUE"
    ACCEPTING_ABOVE_VALUE = "ACCEPTING_ABOVE_VALUE"
    ACCEPTING_BELOW_VALUE = "ACCEPTING_BELOW_VALUE"
    REJECTING_ABOVE_VALUE = "REJECTING_ABOVE_VALUE"
    REJECTING_BELOW_VALUE = "REJECTING_BELOW_VALUE"
    FAILED_ACCEPTANCE_UP = "FAILED_ACCEPTANCE_UP"
    FAILED_ACCEPTANCE_DOWN = "FAILED_ACCEPTANCE_DOWN"
    PRICE_DISCOVERY_UP = "PRICE_DISCOVERY_UP"
    PRICE_DISCOVERY_DOWN = "PRICE_DISCOVERY_DOWN"
    OUTSIDE_RTH = "OUTSIDE_RTH"
    NO_VALUE = "NO_VALUE"


def classify_auction_states(feat: pd.DataFrame, *, value_source: str = "developing") -> pd.Series:
    """
    Sequential state machine using only past+current bar.

    value_source: 'developing' | 'prior' — which VAH/VAL to reference.
    """
    if value_source == "prior":
        vah_col, val_col = "prior_vah", "prior_val"
    else:
        vah_col, val_col = "dev_vah", "dev_val"

    states: list[str] = []
    bars_above = bars_below = closes_above = closes_below = 0
    was_accepting_above = was_accepting_below = False

    for i in range(len(feat)):
        row = feat.iloc[i]
        if not row.get("in_rth", False):
            states.append(AuctionState.OUTSIDE_RTH.value)
            bars_above = bars_below = closes_above = closes_below = 0
            was_accepting_above = was_accepting_below = False
            continue

        vah, val = row[vah_col], row[val_col]
        if np.isnan(vah) or np.isnan(val):
            states.append(AuctionState.NO_VALUE.value)
            continue

        c, h, l = row["close"], row["high"], row["low"]
        inside = val <= c <= vah
        test_above = h > vah and c <= vah
        test_below = l < val and c >= val
        above = c > vah
        below = c < val

        if above:
            bars_above += 1
            closes_above += 1
            bars_below = closes_below = 0
        elif below:
            bars_below += 1
            closes_below += 1
            bars_above = closes_above = 0
        elif inside:
            # rejection sequence detection
            if bars_above > 0 and bars_above <= REJECT_MAX_BARS_OUTSIDE and closes_above < ACCEPT_MIN_CLOSES_OUTSIDE:
                states.append(AuctionState.REJECTING_ABOVE_VALUE.value)
                bars_above = closes_above = 0
                continue
            if bars_below > 0 and bars_below <= REJECT_MAX_BARS_OUTSIDE and closes_below < ACCEPT_MIN_CLOSES_OUTSIDE:
                states.append(AuctionState.REJECTING_BELOW_VALUE.value)
                bars_below = closes_below = 0
                continue
            if was_accepting_above:
                states.append(AuctionState.FAILED_ACCEPTANCE_UP.value)
                was_accepting_above = False
                continue
            if was_accepting_below:
                states.append(AuctionState.FAILED_ACCEPTANCE_DOWN.value)
                was_accepting_below = False
                continue
            bars_above = bars_below = closes_above = closes_below = 0
            width = row.get("dev_value_width", vah - val)
            if not np.isnan(width) and width > 0:
                pos = (c - val) / width
                if 0.35 <= pos <= 0.65:
                    states.append(AuctionState.BALANCED.value)
                else:
                    states.append(AuctionState.ROTATIONAL.value)
            else:
                states.append(AuctionState.BALANCED.value)
            continue

        if test_above:
            states.append(AuctionState.TESTING_UPPER_VALUE.value)
            bars_above += 1
            continue
        if test_below:
            states.append(AuctionState.TESTING_LOWER_VALUE.value)
            bars_below += 1
            continue

        if above and bars_above >= ACCEPT_MIN_BARS_OUTSIDE and closes_above >= ACCEPT_MIN_CLOSES_OUTSIDE:
            was_accepting_above = True
            states.append(AuctionState.ACCEPTING_ABOVE_VALUE.value)
            if row.get("dev_value_width", 0) and c > vah + row["dev_value_width"]:
                states[-1] = AuctionState.PRICE_DISCOVERY_UP.value
            continue
        if below and bars_below >= ACCEPT_MIN_BARS_OUTSIDE and closes_below >= ACCEPT_MIN_CLOSES_OUTSIDE:
            was_accepting_below = True
            states.append(AuctionState.ACCEPTING_BELOW_VALUE.value)
            if row.get("dev_value_width", 0) and c < val - row["dev_value_width"]:
                states[-1] = AuctionState.PRICE_DISCOVERY_DOWN.value
            continue

        states.append(AuctionState.ROTATIONAL.value)

    return pd.Series(states, index=feat.index, name="auction_state")
