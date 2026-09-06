"""Phase76 signal families A–F — causal sequences only."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ACCEPT_MIN_CLOSES_OUTSIDE, REJECT_MAX_BARS_OUTSIDE
from .entry import attach_entries


def _vah_val_cols(value_source: str) -> tuple[str, str]:
    if value_source == "prior":
        return "prior_vah", "prior_val"
    return "dev_vah", "dev_val"


def family_a_upper_rejection(feat: pd.DataFrame, *, value_source: str = "developing") -> pd.DataFrame:
    """TEST_ABOVE_VAH → FAILURE_TO_ACCEPT → CLOSE_BACK_INSIDE → SHORT."""
    vah_col, val_col = _vah_val_cols(value_source)
    rows = []
    testing = False
    bars_out = 0
    for ts, row in feat.iterrows():
        if not row["in_rth"]:
            testing = False
            bars_out = 0
            continue
        vah, val = row[vah_col], row[val_col]
        if np.isnan(vah) or np.isnan(val):
            continue
        c, h = row["close"], row["high"]
        if h > vah and c <= vah:
            testing = True
            bars_out = 1
            continue
        if testing:
            if c > vah:
                bars_out += 1
                if bars_out > REJECT_MAX_BARS_OUTSIDE:
                    testing = False
                continue
            if val <= c <= vah:
                rows.append(
                    {
                        "signal_ts": ts,
                        "direction": "SHORT",
                        "family": "A_UPPER_REJECTION",
                        "value_source": value_source,
                        "level_price": vah,
                        "dist_from_level": c - vah,
                        "reason_codes": "TEST_ABOVE_VAH|FAILURE_TO_ACCEPT|CLOSE_BACK_INSIDE_VALUE|SIGNAL_SHORT",
                    }
                )
                testing = False
                bars_out = 0
    return attach_entries(pd.DataFrame(rows), feat)


def family_b_lower_rejection(feat: pd.DataFrame, *, value_source: str = "developing") -> pd.DataFrame:
    """TEST_BELOW_VAL → FAILURE_TO_ACCEPT → CLOSE_BACK_INSIDE → LONG."""
    vah_col, val_col = _vah_val_cols(value_source)
    rows = []
    testing = False
    bars_out = 0
    for ts, row in feat.iterrows():
        if not row["in_rth"]:
            testing = False
            bars_out = 0
            continue
        vah, val = row[vah_col], row[val_col]
        if np.isnan(vah) or np.isnan(val):
            continue
        c, l = row["close"], row["low"]
        if l < val and c >= val:
            testing = True
            bars_out = 1
            continue
        if testing:
            if c < val:
                bars_out += 1
                if bars_out > REJECT_MAX_BARS_OUTSIDE:
                    testing = False
                continue
            if val <= c <= vah:
                rows.append(
                    {
                        "signal_ts": ts,
                        "direction": "LONG",
                        "family": "B_LOWER_REJECTION",
                        "value_source": value_source,
                        "level_price": val,
                        "dist_from_level": c - val,
                        "reason_codes": "TEST_BELOW_VAL|FAILURE_TO_ACCEPT|CLOSE_BACK_INSIDE_VALUE|SIGNAL_LONG",
                    }
                )
                testing = False
                bars_out = 0
    return attach_entries(pd.DataFrame(rows), feat)


def family_c_initiative_acceptance(feat: pd.DataFrame, *, value_source: str = "developing") -> pd.DataFrame:
    """Break → remain outside → acceptance → retest holds → signal in break direction."""
    vah_col, val_col = _vah_val_cols(value_source)
    rows = []
    mode = None  # UP / DOWN
    accept_bars = 0
    accept_closes = 0
    waiting_retest = False
    for ts, row in feat.iterrows():
        if not row["in_rth"]:
            mode = None
            waiting_retest = False
            continue
        vah, val = row[vah_col], row[val_col]
        if np.isnan(vah) or np.isnan(val):
            continue
        c, l, h = row["close"], row["low"], row["high"]
        if mode is None:
            if c > vah:
                mode = "UP"
                accept_bars = 1
                accept_closes = 1
            elif c < val:
                mode = "DOWN"
                accept_bars = 1
                accept_closes = 1
            continue
        if mode == "UP":
            if c > vah:
                accept_bars += 1
                accept_closes += 1
                if accept_bars >= 3 and accept_closes >= ACCEPT_MIN_CLOSES_OUTSIDE:
                    waiting_retest = True
                continue
            if waiting_retest and l <= vah and c > vah:
                rows.append(
                    {
                        "signal_ts": ts,
                        "direction": "LONG",
                        "family": "C_INITIATIVE_ACCEPTANCE",
                        "value_source": value_source,
                        "level_price": vah,
                        "dist_from_level": c - vah,
                        "reason_codes": "ACCEPT_ABOVE_VALUE|RETEST_HOLD|SIGNAL_LONG",
                    }
                )
                mode = None
                waiting_retest = False
            else:
                mode = None
                waiting_retest = False
        elif mode == "DOWN":
            if c < val:
                accept_bars += 1
                accept_closes += 1
                if accept_bars >= 3 and accept_closes >= ACCEPT_MIN_CLOSES_OUTSIDE:
                    waiting_retest = True
                continue
            if waiting_retest and h >= val and c < val:
                rows.append(
                    {
                        "signal_ts": ts,
                        "direction": "SHORT",
                        "family": "C_INITIATIVE_ACCEPTANCE",
                        "value_source": value_source,
                        "level_price": val,
                        "dist_from_level": c - val,
                        "reason_codes": "ACCEPT_BELOW_VALUE|RETEST_HOLD|SIGNAL_SHORT",
                    }
                )
                mode = None
                waiting_retest = False
            else:
                mode = None
                waiting_retest = False
    return attach_entries(pd.DataFrame(rows), feat)


def family_d_failed_acceptance(feat: pd.DataFrame, *, value_source: str = "developing") -> pd.DataFrame:
    """Accepted outside → loses boundary → failure confirmed → opposite signal."""
    vah_col, val_col = _vah_val_cols(value_source)
    rows = []
    accepted_up = accepted_down = False
    for ts, row in feat.iterrows():
        if not row["in_rth"]:
            accepted_up = accepted_down = False
            continue
        vah, val = row[vah_col], row[val_col]
        if np.isnan(vah) or np.isnan(val):
            continue
        c = row["close"]
        if not accepted_up and c > vah:
            accepted_up = True
            continue
        if accepted_up and c < vah and c >= val:
            rows.append(
                {
                    "signal_ts": ts,
                    "direction": "SHORT",
                    "family": "D_FAILED_ACCEPTANCE",
                    "value_source": value_source,
                    "level_price": vah,
                    "dist_from_level": c - vah,
                    "reason_codes": "FAILED_ACCEPTANCE_UP|VALUE_REENTRY|SIGNAL_SHORT",
                }
            )
            accepted_up = False
            continue
        if not accepted_down and c < val:
            accepted_down = True
            continue
        if accepted_down and c > val and c <= vah:
            rows.append(
                {
                    "signal_ts": ts,
                    "direction": "LONG",
                    "family": "D_FAILED_ACCEPTANCE",
                    "value_source": value_source,
                    "level_price": val,
                    "dist_from_level": c - val,
                    "reason_codes": "FAILED_ACCEPTANCE_DOWN|VALUE_REENTRY|SIGNAL_LONG",
                }
            )
            accepted_down = False
    return attach_entries(pd.DataFrame(rows), feat)


def family_e_lvn_traversal(feat: pd.DataFrame) -> pd.DataFrame:
    """LVN traversal — only if in_lvn causally observed."""
    if "in_lvn" not in feat.columns or not feat["in_lvn"].any():
        return pd.DataFrame(
            columns=["signal_ts", "direction", "family", "reason_codes"]
        ).assign(reason_codes="LVN_DATA_INSUFFICIENT")
    rows = []
    in_lvn_run = 0
    direction = None
    for ts, row in feat.iterrows():
        if not row["in_rth"]:
            in_lvn_run = 0
            direction = None
            continue
        if row["in_lvn"]:
            in_lvn_run += 1
            if in_lvn_run == 1:
                direction = "LONG" if row["close"] >= row.get("dev_poc", row["close"]) else "SHORT"
            elif in_lvn_run >= 2 and direction:
                rows.append(
                    {
                        "signal_ts": ts,
                        "direction": direction,
                        "family": "E_LVN_TRAVERSAL",
                        "value_source": "developing",
                        "level_price": np.nan,
                        "dist_from_level": np.nan,
                        "reason_codes": "LVN_TRAVERSAL|SIGNAL_" + direction,
                    }
                )
                in_lvn_run = 0
                direction = None
        else:
            in_lvn_run = 0
            direction = None
    return attach_entries(pd.DataFrame(rows), feat)


def family_f_value_rotation(feat: pd.DataFrame, *, value_source: str = "developing") -> pd.DataFrame:
    """Balanced/rotational: extreme rejection → signal toward POC."""
    vah_col, val_col = _vah_val_cols(value_source)
    poc_col = "dev_poc" if value_source == "developing" else "prior_poc"
    rows = []
    for ts, row in feat.iterrows():
        if not row["in_rth"]:
            continue
        state = row.get("auction_state", "")
        if state not in ("BALANCED", "ROTATIONAL"):
            continue
        vah, val, poc = row[vah_col], row[val_col], row[poc_col]
        if np.isnan(vah) or np.isnan(val) or np.isnan(poc):
            continue
        c, h, l = row["close"], row["high"], row["low"]
        if h > vah and val <= c <= vah:
            rows.append(
                {
                    "signal_ts": ts,
                    "direction": "SHORT",
                    "family": "F_VALUE_ROTATION",
                    "value_source": value_source,
                    "level_price": poc,
                    "dist_from_level": c - poc,
                    "reason_codes": "VALUE_ROTATION|REJECT_ABOVE_VALUE|POC_TARGET|SIGNAL_SHORT",
                }
            )
        elif l < val and val <= c <= vah:
            rows.append(
                {
                    "signal_ts": ts,
                    "direction": "LONG",
                    "family": "F_VALUE_ROTATION",
                    "value_source": value_source,
                    "level_price": poc,
                    "dist_from_level": c - poc,
                    "reason_codes": "VALUE_ROTATION|REJECT_BELOW_VALUE|POC_TARGET|SIGNAL_LONG",
                }
            )
    return attach_entries(pd.DataFrame(rows), feat)
