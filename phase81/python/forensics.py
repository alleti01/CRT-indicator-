"""Short failure forensics (diagnostic labels)."""
from __future__ import annotations

import pandas as pd


def classify_short_failures(shorts: pd.DataFrame, feat: pd.DataFrame) -> pd.DataFrame:
    m = shorts.merge(feat, on="trade_id", how="inner")
    labels = []
    for _, r in m.iterrows():
        net_r = float(r["net_R_m1"])
        mfe = float(r.get("MFE_R_m1", 0))
        mae = float(r.get("MAE_R_m1", 0))
        lbl = "AMBIGUOUS"
        if net_r >= 1.5:
            lbl = "GOOD_SHORT_BAD_STOP" if mfe >= 2.0 and net_r < 2.0 else "GOOD_SHORT"
            if lbl == "GOOD_SHORT":
                labels.append(lbl)
                continue
        if r.get("late_chase"):
            lbl = "LATE_EXTENSION"
        elif r.get("market_state") == "UNCERTAIN" and r.get("countertrend_ratio", 1) >= 0.75:
            lbl = "CHOP_SHORT"
        elif not r.get("displacement") and not r.get("breakdown_10") and r.get("body_atr", 0) < 0.3:
            lbl = "NO_BEARISH_COMMITMENT"
        elif r.get("breakdown_10") and net_r <= -0.9 and mfe < 0.5:
            lbl = "FAILED_BREAKDOWN"
        elif r.get("move_down_5", 0) < 0.25 and r.get("extension_atr", 0) < 0.5:
            lbl = "EARLY_SHORT"
        elif r.get("bounce_fail") and net_r <= -0.5:
            lbl = "CONTINUATION_MISSED" if mfe < 0.3 else "FAILED_BOUNCE_MISSED"
        elif not r.get("aligned_active") and r.get("5m_state") == "BULLISH":
            lbl = "LONG_FAILURE_NO_SHORT"
        elif net_r <= -0.9:
            lbl = "EARLY_SHORT" if mae < 1.0 else "CHOP_SHORT"
        labels.append(lbl)
    m["failure_category"] = labels
    m.loc[m["net_R_m1"] >= 2.0, "failure_category"] = "GOOD_SHORT"
    return m
