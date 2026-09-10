"""Causal short entry features at signal time (no future bars)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_short_features(df: pd.DataFrame, m) -> pd.DataFrame:
    """Pre-entry causal features for each SHORT row. Signal bar = entry_i - 1."""
    rows = []
    hi, lo, cl, op = m.hi, m.lo, m.cl, m.op
    n = m.n
    for _, row in df.iterrows():
        ei = int(row["entry_i_m1"])
        sig = ei - 1
        if sig < 10 or ei >= n - 65:
            continue
        atr = float(row["atr"]) if float(row["atr"]) > 0 else 1.0
        ep = float(row["entry_price_m1"])

        lb5 = max(0, sig - 5)
        lb10 = max(0, sig - 10)
        lb15 = max(0, sig - 15)
        roll_hi_5 = float(np.max(hi[lb5 : sig + 1]))
        roll_lo_5 = float(np.min(lo[lb5 : sig + 1]))
        roll_hi_10 = float(np.max(hi[lb10 : sig + 1]))
        roll_lo_10 = float(np.min(lo[lb10 : sig + 1]))
        roll_hi_15 = float(np.max(hi[lb15 : sig + 1]))

        body = float(cl[sig] - op[sig])
        rng = float(hi[sig] - lo[sig]) if hi[sig] > lo[sig] else 1e-9
        bearish_bar = body < 0
        body_atr = abs(body) / atr
        range_atr = rng / atr
        close_loc = (cl[sig] - lo[sig]) / rng  # 0=low, 1=high

        micro_bos_5 = cl[sig] < float(np.min(lo[lb5:sig])) if sig > lb5 else False
        micro_bos_8 = cl[sig] < float(np.min(lo[max(0, sig - 8) : sig])) if sig >= 8 else False

        # Breakdown: close below prior 10-bar low (excluding signal bar)
        breakdown_10 = cl[sig] < float(np.min(lo[lb10:sig])) if sig > lb10 else False

        # Extension: drop from recent high before entry
        extension_atr = (roll_hi_10 - ep) / atr
        move_down_5 = (roll_hi_5 - cl[sig]) / atr

        # Bounce failure proxy: prior 3 bars up then bearish signal
        if sig >= 3:
            prior_up = sum(cl[sig - k] > cl[sig - k - 1] for k in range(1, 4))
            bounce_fail = prior_up >= 2 and bearish_bar and cl[sig] < op[sig - 1]
        else:
            bounce_fail = False

        # Failed reclaim: high pierced prior high but closed below prior close
        if sig >= 2:
            failed_reclaim = hi[sig] > hi[sig - 1] and cl[sig] < cl[sig - 1] and bearish_bar
        else:
            failed_reclaim = False

        # Displacement confirmation
        displacement = body_atr >= 0.5 and bearish_bar and close_loc <= 0.35

        # Anti-chase: already extended down
        late_chase = move_down_5 >= 1.5 or extension_atr >= 2.0

        # Early/chop proxies from parquet fields
        rows.append({
            "trade_id": row["trade_id"],
            "entry_i_m1": ei,
            "bearish_bar": bearish_bar,
            "body_atr": body_atr,
            "range_atr": range_atr,
            "close_loc": close_loc,
            "micro_bos_5": micro_bos_5,
            "micro_bos_8": micro_bos_8,
            "breakdown_10": breakdown_10,
            "extension_atr": extension_atr,
            "move_down_5": move_down_5,
            "bounce_fail": bounce_fail,
            "failed_reclaim": failed_reclaim,
            "displacement": displacement,
            "late_chase": late_chase,
            "good_location": bool(row.get("good_location", False)),
            "reaction_score": float(row.get("reaction_score", 0)),
            "location_score": float(row.get("location_score", 0)),
            "false_rev_low": row.get("false_reversal_risk") == "LOW",
            "reversal_strong": row.get("reversal_support") == "STRONG",
            "htf_contra": bool(row.get("htf_contra_code", False)),
            "pullback_conflict": bool(row.get("pullback_conflict", False)),
            "aligned_active": bool(row.get("aligned_with_active", False)),
            "market_reversal": row.get("market_state") == "REVERSAL_TRANSITION",
            "m5_bearish": row.get("5m_state") == "BEARISH",
            "m15_bearish": row.get("15m_state") == "BEARISH",
            "m5_not_neutral": row.get("5m_state") != "NEUTRAL",
        })
    return pd.DataFrame(rows)
