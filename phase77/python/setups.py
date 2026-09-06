"""Phase77 complete framework setups O1–O6 + confluence scoring."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ENTRY_DELAY_BARS


SETUP_CODES = ("O1", "O2", "O3", "O4", "O5", "O6")


def _layer_flags(row: pd.Series, direction: str) -> dict[str, bool]:
    """Seven semantic layers aligned with setup direction."""
    is_long = direction == "LONG"
    auc = row.get("auction_state", "")
    loc = row.get("location_type", "")
    struct = row.get("structure_state", "")
    pr = row.get("price_response", "")
    abs_p = row.get("absorption_proxy", "")
    acc = row.get("acceptance_state", "")
    conf = row.get("confirmation_state", "")

    if is_long:
        auction_ok = auc in (
            "LOWER_EXTREME_TEST", "PRICE_DISCOVERY_DOWN", "FAILED_DISCOVERY_DOWN",
            "RETURN_TO_VALUE", "BALANCE",
        ) or row.get("auction_direction") == "DOWN"
        loc_ok = loc in ("LOWER_VALUE_EXTREME", "OUTSIDE_VALUE_DOWN", "PRIOR_EXTREME", "LVN_ZONE")
        struct_ok = struct in (
            "IMPULSE_DOWN", "EXTENDED_DOWN", "CONTROLLED_RETRACE_AFTER_DOWN",
            "RESUMPTION_DOWN", "FAILED_CONTINUATION_DOWN", "STRUCTURE_TRANSITION_UP",
        )
        of_ok = (row.get("delta_norm_60s") or 0) < -0.1 or (row.get("sell_vol_60s") or 0) > (row.get("buy_vol_60s") or 0)
        pr_ok = pr in ("SELLING_EFFICIENT", "SELLING_INEFFICIENT", "BUYING_INEFFICIENT")
        abs_ok = abs_p in ("SELLING_ABSORBED_PROXY", "SELLING_EXHAUSTING", "BUYING_ABSORBED_PROXY")
        acc_ok = acc in ("LOWER_REJECTION", "ACCEPTANCE_UP", "FAILED_ACCEPTANCE_DOWN")
        conf_ok = conf in ("CONFIRMED_LONG",)
    else:
        auction_ok = auc in (
            "UPPER_EXTREME_TEST", "PRICE_DISCOVERY_UP", "FAILED_DISCOVERY_UP",
        ) or row.get("auction_direction") == "UP"
        loc_ok = loc in ("UPPER_VALUE_EXTREME", "OUTSIDE_VALUE_UP", "PRIOR_EXTREME", "HVN_ZONE", "LVN_ZONE")
        struct_ok = struct in (
            "IMPULSE_UP", "EXTENDED_UP", "CONTROLLED_RETRACE_AFTER_UP",
            "RESUMPTION_UP", "FAILED_CONTINUATION_UP", "DIMINISHING_UP_IMPULSES",
        )
        of_ok = (row.get("delta_norm_60s") or 0) > 0.1 or (row.get("buy_vol_60s") or 0) > (row.get("sell_vol_60s") or 0)
        pr_ok = pr in ("BUYING_INEFFICIENT", "BUYING_EFFICIENT", "SELLING_INEFFICIENT")
        abs_ok = abs_p in ("BUYING_ABSORBED_PROXY", "BUYING_EXHAUSTING", "SELLING_ABSORBED_PROXY")
        acc_ok = acc in ("UPPER_REJECTION", "ACCEPTANCE_DOWN", "FAILED_ACCEPTANCE_UP")
        conf_ok = conf in ("CONFIRMED_SHORT",)

    return {
        "auction": auction_ok,
        "location": loc_ok,
        "structure": struct_ok,
        "order_flow": of_ok,
        "price_response": pr_ok,
        "acceptance_rejection": acc_ok,
        "confirmation": conf_ok,
    }


def confluence_count(row: pd.Series, direction: str) -> int:
    return sum(_layer_flags(row, direction).values())


def detect_setups(feat: pd.DataFrame) -> pd.DataFrame:
    """Detect O1–O6 at confirmation bar; entry = open T+1."""
    idx = feat.index
    rows: list[dict] = []

    for i in range(len(feat) - ENTRY_DELAY_BARS):
        row = feat.iloc[i]
        if not row.get("in_rth", False):
            continue
        conf = row.get("confirmation_state", "")
        if conf not in ("CONFIRMED_LONG", "CONFIRMED_SHORT"):
            continue
        direction = "LONG" if conf == "CONFIRMED_LONG" else "SHORT"
        flags = _layer_flags(row, direction)
        cc = sum(flags.values())

        setup = None
        auc = row.get("auction_state", "")
        acc = row.get("acceptance_state", "")
        abs_p = row.get("absorption_proxy", "")
        pr = row.get("price_response", "")

        if direction == "SHORT":
            if (
                auc in ("UPPER_EXTREME_TEST", "PRICE_DISCOVERY_UP", "FAILED_DISCOVERY_UP")
                and flags["location"]
                and row.get("structure_maturity", 0) >= 0.5
                and flags["order_flow"]
                and pr in ("BUYING_INEFFICIENT",)
                and abs_p in ("BUYING_ABSORBED_PROXY", "BUYING_EXHAUSTING")
                and acc == "UPPER_REJECTION"
            ):
                setup = "O1"
            elif acc == "ACCEPTANCE_DOWN" and flags["structure"] and flags["order_flow"] and pr == "SELLING_EFFICIENT":
                setup = "O4"
            elif acc == "FAILED_ACCEPTANCE_UP" and flags["structure"]:
                setup = "O5"
        else:
            if (
                auc in ("LOWER_EXTREME_TEST", "PRICE_DISCOVERY_DOWN", "FAILED_DISCOVERY_DOWN")
                and flags["location"]
                and row.get("structure_maturity", 0) >= 0.5
                and flags["order_flow"]
                and pr in ("SELLING_INEFFICIENT",)
                and abs_p in ("SELLING_ABSORBED_PROXY", "SELLING_EXHAUSTING")
                and acc == "LOWER_REJECTION"
            ):
                setup = "O2"
            elif acc == "ACCEPTANCE_UP" and flags["structure"] and flags["order_flow"] and pr == "BUYING_EFFICIENT":
                setup = "O3"
            elif acc == "FAILED_ACCEPTANCE_DOWN" and flags["structure"]:
                setup = "O6"

        if setup is None:
            continue

        entry_i = i + ENTRY_DELAY_BARS
        entry_ts = idx[entry_i]
        rows.append({
            "signal_ts": idx[i],
            "entry_ts": entry_ts,
            "setup": setup,
            "direction": direction,
            "entry_price": float(feat.iloc[entry_i]["open"]),
            "atr": float(row["atr"]),
            "confluence_count": cc,
            "auction_state": row["auction_state"],
            "location_type": row["location_type"],
            "structure_state": row["structure_state"],
            "price_response": row["price_response"],
            "absorption_proxy": row["absorption_proxy"],
            "acceptance_state": row["acceptance_state"],
            "confirmation_state": conf,
            "dev_vah": row.get("dev_vah"),
            "dev_val": row.get("dev_val"),
            "dev_poc": row.get("dev_poc"),
            "dev_vwap": row.get("dev_vwap"),
            "in_hvn": row.get("in_hvn"),
            "in_lvn": row.get("in_lvn"),
            "delta_norm_60s": row.get("delta_norm_60s"),
            "buy_vol_60s": row.get("buy_vol_60s"),
            "sell_vol_60s": row.get("sell_vol_60s"),
            "known_at": idx[i],
            **{f"layer_{k}": v for k, v in flags.items()},
        })

    return pd.DataFrame(rows)


def ablation_masks(signals: pd.DataFrame) -> dict[str, pd.Series]:
    layers = ("auction", "location", "structure", "order_flow", "price_response", "acceptance_rejection", "confirmation")
    masks = {"FULL": pd.Series(True, index=signals.index)}
    for drop in layers:
        others = [f"layer_{l}" for l in layers if l != drop and f"layer_{l}" in signals.columns]
        if others:
            masks[f"FULL_minus_{drop.upper()}"] = signals[others].all(axis=1)
    return masks
