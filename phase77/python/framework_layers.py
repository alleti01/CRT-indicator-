"""Phase77 framework layers 1–8 — strictly causal, bar-sequential."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import (
    ABSORPTION_MAX_UP_DISP,
    ABSORPTION_MIN_BUY_NORM,
    ACCEPT_MIN_BARS_OUTSIDE,
    ACCEPT_MIN_CLOSES_OUTSIDE,
    CONFIRMATION_SWING_BARS,
    EFFICIENT_DISP_PER_NORM_DELTA,
    IMPULSE_MIN_ATR,
    INEFFICIENT_DISP_PER_NORM_DELTA,
    OF_PRIMARY_SEC,
    REJECT_MAX_BARS_OUTSIDE,
    RETRACE_MAX_RATIO,
    RETRACE_MIN_RATIO,
    SWING_LOOKBACK,
)
from phase68.python.micro_primitives import build_minute_grid


def attach_order_flow(feat: pd.DataFrame, trades: pd.DataFrame, m1: pd.DataFrame) -> pd.DataFrame:
    of = build_minute_grid(trades, m1)
    overlap = [c for c in of.columns if c in feat.columns]
    of = of.drop(columns=overlap, errors="ignore")
    return feat.join(of, how="left")


def build_framework_layers(feat: pd.DataFrame) -> pd.DataFrame:
    """Add auction, location, structure, price_response, absorption, acceptance, confirmation."""
    out = feat.copy()
    n = len(out)

    auction_state = []
    auction_dir = []
    auction_strength = []
    location_type = []
    structure_state = []
    structure_dir = []
    structure_maturity = []
    extension_atr = []
    retracement_atr = []
    price_response = []
    absorption_proxy = []
    acceptance_state = []
    confirmation_state = []

    bars_above = bars_below = closes_above = closes_below = 0
    impulse_dir = 0
    impulse_start = np.nan
    impulse_ext = 0.0
    retrace_ext = 0.0
    swing_high = np.nan
    swing_low = np.nan

    w = OF_PRIMARY_SEC
    dn_col = f"delta_norm_{w}s"
    disp_col = f"price_disp_{w}s"
    buy_col = f"buy_vol_{w}s"
    sell_col = f"sell_vol_{w}s"
    pace_col = f"pace_{w}s"

    for i in range(n):
        row = out.iloc[i]
        atr = row.get("atr", np.nan)
        if pd.isna(atr) or atr <= 0 or not row.get("in_rth", False):
            auction_state.append("OUTSIDE_RTH")
            auction_dir.append("NEUTRAL")
            auction_strength.append(0.0)
            location_type.append("NO_IMPORTANT_LOCATION")
            structure_state.append("UNRESOLVED")
            structure_dir.append("NEUTRAL")
            structure_maturity.append(0.0)
            extension_atr.append(0.0)
            retracement_atr.append(0.0)
            price_response.append("NEUTRAL_RESPONSE")
            absorption_proxy.append("NONE")
            acceptance_state.append("UNRESOLVED")
            confirmation_state.append("NO_CONFIRMATION")
            continue

        c, h, l = row["close"], row["high"], row["low"]
        vah, val = row.get("dev_vah", np.nan), row.get("dev_val", np.nan)
        poc = row.get("dev_poc", np.nan)

        # --- Layer 1: Auction context ---
        a_state = "BALANCE"
        a_dir = "NEUTRAL"
        a_str = 0.0
        if not (pd.isna(vah) or pd.isna(val)):
            width = vah - val
            if c > vah:
                bars_above += 1
                closes_above += 1
                bars_below = closes_below = 0
                a_state = "PRICE_DISCOVERY_UP"
                a_dir = "UP"
                a_str = min((c - vah) / atr, 3.0)
            elif c < val:
                bars_below += 1
                closes_below += 1
                bars_above = closes_above = 0
                a_state = "PRICE_DISCOVERY_DOWN"
                a_dir = "DOWN"
                a_str = min((val - c) / atr, 3.0)
            elif val <= c <= vah:
                if h > vah and c <= vah:
                    a_state = "UPPER_EXTREME_TEST"
                    a_dir = "UP"
                elif l < val and c >= val:
                    a_state = "LOWER_EXTREME_TEST"
                    a_dir = "DOWN"
                elif width > 0:
                    pos = (c - val) / width
                    if 0.35 <= pos <= 0.65:
                        a_state = "BALANCE"
                    else:
                        a_state = "ROTATION"
                if bars_above > 0 and bars_above <= REJECT_MAX_BARS_OUTSIDE:
                    a_state = "FAILED_DISCOVERY_UP"
                if bars_below > 0 and bars_below <= REJECT_MAX_BARS_OUTSIDE:
                    a_state = "FAILED_DISCOVERY_DOWN"
                bars_above = bars_below = closes_above = closes_below = 0

        if bars_above >= ACCEPT_MIN_BARS_OUTSIDE and closes_above >= ACCEPT_MIN_CLOSES_OUTSIDE:
            a_state = "PRICE_DISCOVERY_UP"
            a_dir = "UP"
        if bars_below >= ACCEPT_MIN_BARS_OUTSIDE and closes_below >= ACCEPT_MIN_CLOSES_OUTSIDE:
            a_state = "PRICE_DISCOVERY_DOWN"
            a_dir = "DOWN"

        # --- Layer 2: Location (Phase76: HVN = activity context only) ---
        loc = "ORDINARY_SR"
        band = 0.25 * atr
        if row.get("in_hvn"):
            loc = "HVN_ZONE"
        elif row.get("in_lvn"):
            loc = "LVN_ZONE"
        elif not pd.isna(vah) and abs(c - vah) <= band:
            loc = "UPPER_VALUE_EXTREME"
        elif not pd.isna(val) and abs(c - val) <= band:
            loc = "LOWER_VALUE_EXTREME"
        elif not pd.isna(poc) and abs(c - poc) <= band:
            loc = "VALUE_CENTER"
        elif not pd.isna(vah) and c > vah:
            loc = "OUTSIDE_VALUE_UP"
        elif not pd.isna(val) and c < val:
            loc = "OUTSIDE_VALUE_DOWN"
        elif not pd.isna(row.get("prior_high")) and abs(c - row["prior_high"]) <= band:
            loc = "PRIOR_EXTREME"
        elif not pd.isna(row.get("prior_low")) and abs(c - row["prior_low"]) <= band:
            loc = "PRIOR_EXTREME"

        # --- Layer 3: Structure (causal impulse/retrace) ---
        if i >= 1:
            disp = (c - out.iloc[i - 1]["close"]) / atr
        else:
            disp = 0.0
        s_state = "UNRESOLVED"
        s_dir = "NEUTRAL"
        s_mat = 0.0
        ext_a = abs(disp)
        ret_a = 0.0

        if impulse_dir == 0 and abs(disp) >= IMPULSE_MIN_ATR / 5:
            impulse_dir = 1 if disp > 0 else -1
            impulse_start = c
            impulse_ext = abs(disp)
            s_state = "IMPULSE_UP" if impulse_dir > 0 else "IMPULSE_DOWN"
            s_dir = "UP" if impulse_dir > 0 else "DOWN"
        elif impulse_dir != 0:
            move_from_start = (c - impulse_start) / atr if impulse_start else 0
            if impulse_dir > 0:
                if move_from_start >= impulse_ext:
                    impulse_ext = move_from_start
                    s_state = "IMPULSE_UP" if impulse_ext < IMPULSE_MIN_ATR * 2 else "EXTENDED_UP"
                elif move_from_start < impulse_ext * (1 - RETRACE_MIN_RATIO):
                    retrace_ext = impulse_ext - move_from_start
                    ratio = retrace_ext / max(impulse_ext, 0.01)
                    if RETRACE_MIN_RATIO <= ratio <= RETRACE_MAX_RATIO:
                        s_state = "CONTROLLED_RETRACE_AFTER_UP"
                    elif ratio > RETRACE_MAX_RATIO:
                        s_state = "FAILED_CONTINUATION_UP"
                        impulse_dir = 0
                    ret_a = retrace_ext
                elif move_from_start > impulse_ext * 0.5 and i > 0:
                    s_state = "RESUMPTION_UP"
            else:
                if abs(move_from_start) >= impulse_ext:
                    impulse_ext = abs(move_from_start)
                    s_state = "IMPULSE_DOWN" if impulse_ext < IMPULSE_MIN_ATR * 2 else "EXTENDED_DOWN"
                elif abs(move_from_start) < impulse_ext * (1 - RETRACE_MIN_RATIO):
                    retrace_ext = impulse_ext - abs(move_from_start)
                    ratio = retrace_ext / max(impulse_ext, 0.01)
                    if RETRACE_MIN_RATIO <= ratio <= RETRACE_MAX_RATIO:
                        s_state = "CONTROLLED_RETRACE_AFTER_DOWN"
                    elif ratio > RETRACE_MAX_RATIO:
                        s_state = "FAILED_CONTINUATION_DOWN"
                        impulse_dir = 0
                    ret_a = retrace_ext
                elif abs(move_from_start) > impulse_ext * 0.5:
                    s_state = "RESUMPTION_DOWN"
            s_dir = "UP" if impulse_dir > 0 else "DOWN"
            s_mat = min(impulse_ext, 3.0)
            ext_a = impulse_ext

        # --- Layer 5: Price response ---
        dn = row.get(dn_col, 0) or 0
        pdisp = row.get(disp_col, 0) or 0
        pr = "NEUTRAL_RESPONSE"
        if abs(dn) > 0.15:
            eff = abs(pdisp) / max(abs(dn), 0.01)
            if dn > 0 and eff >= EFFICIENT_DISP_PER_NORM_DELTA and pdisp > 0:
                pr = "BUYING_EFFICIENT"
            elif dn > 0 and eff <= INEFFICIENT_DISP_PER_NORM_DELTA:
                pr = "BUYING_INEFFICIENT"
            elif dn < 0 and eff >= EFFICIENT_DISP_PER_NORM_DELTA and pdisp < 0:
                pr = "SELLING_EFFICIENT"
            elif dn < 0 and eff <= INEFFICIENT_DISP_PER_NORM_DELTA:
                pr = "SELLING_INEFFICIENT"

        # --- Layer 6: Absorption proxy ---
        abs_p = "NONE"
        if loc in ("UPPER_VALUE_EXTREME", "OUTSIDE_VALUE_UP", "PRIOR_EXTREME") and dn > ABSORPTION_MIN_BUY_NORM and pdisp < ABSORPTION_MAX_UP_DISP:
            abs_p = "BUYING_ABSORBED_PROXY"
        elif loc in ("LOWER_VALUE_EXTREME", "OUTSIDE_VALUE_DOWN") and dn < -ABSORPTION_MIN_BUY_NORM and pdisp > -ABSORPTION_MAX_UP_DISP:
            abs_p = "SELLING_ABSORBED_PROXY"
        elif dn > 0.3 and pdisp < 0.05:
            abs_p = "BUYING_EXHAUSTING"
        elif dn < -0.3 and pdisp > -0.05:
            abs_p = "SELLING_EXHAUSTING"

        # --- Layer 7: Acceptance / rejection ---
        acc = "UNRESOLVED"
        if a_state == "UPPER_EXTREME_TEST" and pr in ("BUYING_INEFFICIENT",) and abs_p == "BUYING_ABSORBED_PROXY":
            acc = "UPPER_REJECTION"
        elif a_state == "LOWER_EXTREME_TEST" and pr in ("SELLING_INEFFICIENT",) and abs_p == "SELLING_ABSORBED_PROXY":
            acc = "LOWER_REJECTION"
        elif c > vah and bars_above >= ACCEPT_MIN_BARS_OUTSIDE:
            acc = "ACCEPTANCE_UP"
        elif c < val and bars_below >= ACCEPT_MIN_BARS_OUTSIDE:
            acc = "ACCEPTANCE_DOWN"
        elif a_state == "FAILED_DISCOVERY_UP":
            acc = "FAILED_ACCEPTANCE_UP"
        elif a_state == "FAILED_DISCOVERY_DOWN":
            acc = "FAILED_ACCEPTANCE_DOWN"

        # --- Layer 8: Confirmation ---
        if i >= CONFIRMATION_SWING_BARS:
            wh = out["high"].iloc[i - CONFIRMATION_SWING_BARS : i].max()
            wl = out["low"].iloc[i - CONFIRMATION_SWING_BARS : i].min()
        else:
            wh, wl = h, l
        conf = "NO_CONFIRMATION"
        if c < wl and acc in ("UPPER_REJECTION", "FAILED_ACCEPTANCE_UP"):
            conf = "CONFIRMED_SHORT"
        elif c > wh and acc in ("LOWER_REJECTION", "FAILED_ACCEPTANCE_DOWN"):
            conf = "CONFIRMED_LONG"
        elif c > wh and acc == "ACCEPTANCE_UP" and s_state in ("IMPULSE_UP", "RESUMPTION_UP", "EXTENDED_UP"):
            conf = "CONFIRMED_LONG"
        elif c < wl and acc == "ACCEPTANCE_DOWN" and s_state in ("IMPULSE_DOWN", "RESUMPTION_DOWN", "EXTENDED_DOWN"):
            conf = "CONFIRMED_SHORT"
        elif c > wh and s_state == "RESUMPTION_UP":
            conf = "DEVELOPING_LONG"
        elif c < wl and s_state == "RESUMPTION_DOWN":
            conf = "DEVELOPING_SHORT"

        auction_state.append(a_state)
        auction_dir.append(a_dir)
        auction_strength.append(float(a_str))
        location_type.append(loc)
        structure_state.append(s_state)
        structure_dir.append(s_dir)
        structure_maturity.append(float(s_mat))
        extension_atr.append(float(ext_a))
        retracement_atr.append(float(ret_a))
        price_response.append(pr)
        absorption_proxy.append(abs_p)
        acceptance_state.append(acc)
        confirmation_state.append(conf)

    out["auction_state"] = auction_state
    out["auction_direction"] = auction_dir
    out["auction_strength"] = auction_strength
    out["location_type"] = location_type
    out["structure_state"] = structure_state
    out["structure_direction"] = structure_dir
    out["structure_maturity"] = structure_maturity
    out["extension_atr"] = extension_atr
    out["retracement_atr"] = retracement_atr
    out["price_response"] = price_response
    out["absorption_proxy"] = absorption_proxy
    out["acceptance_state"] = acceptance_state
    out["confirmation_state"] = confirmation_state
    out["delta_norm_60s"] = out.get(f"delta_norm_{OF_PRIMARY_SEC}s", np.nan)
    out["buy_vol_60s"] = out.get(f"buy_vol_{OF_PRIMARY_SEC}s", np.nan)
    out["sell_vol_60s"] = out.get(f"sell_vol_{OF_PRIMARY_SEC}s", np.nan)
    out["trade_pace_60s"] = out.get(f"pace_{OF_PRIMARY_SEC}s", np.nan)
    return out
