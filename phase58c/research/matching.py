"""Match 5M ARM/TAKE to 1M opportunity clusters."""
from __future__ import annotations

import numpy as np
import pandas as pd


def match_5m_to_1m(
    opps_1m: pd.DataFrame,
    setups_5m: pd.DataFrame,
    takes_5m: pd.DataFrame,
    m5_signal_m1_i: np.ndarray,
    match_window: int = 30,
    disagree_window: int = 15,
) -> pd.DataFrame:
    """Classify each 5M TAKE vs 1M opportunities."""
    if takes_5m.empty or opps_1m.empty:
        return pd.DataFrame()

    # Index 1M opps by direction for fast lookup
    opp_by_dir = {d: opps_1m.loc[opps_1m["direction"] == d].reset_index(drop=True) for d in ["LONG", "SHORT"]}
    setup_map = setups_5m.set_index("setup_id").to_dict("index") if not setups_5m.empty else {}

    rows = []
    for _, tk in takes_5m.iterrows():
        sid = tk["setup_id"]
        d = tk["direction"]
        take_j = int(tk["take_j"])
        sig_m1 = int(tk["signal_m1_i"])
        setup = setup_map.get(sid, {})
        arm_j = int(setup.get("armed_j", -1))
        arm_m1 = int(m5_signal_m1_i[arm_j]) if arm_j >= 0 and arm_j < len(m5_signal_m1_i) else sig_m1

        opps_d = opp_by_dir.get(d, pd.DataFrame())
        # SAME direction overlap
        classification = "5M_ONLY"
        matched_opp = ""
        if not opps_d.empty:
            overlap = opps_d[
                (opps_d["first_signal_i"] <= sig_m1 + match_window)
                & (opps_d["last_signal_i"] >= sig_m1 - match_window)
            ]
            if len(overlap) == 1:
                classification = "SAME_OPPORTUNITY"
                matched_opp = overlap.iloc[0]["opportunity_id"]
            elif len(overlap) > 1:
                classification = "AMBIGUOUS_MATCH"
                matched_opp = overlap.iloc[0]["opportunity_id"]
            else:
                # Check timing vs nearest opp
                opps_d = opps_d.copy()
                opps_d["dist"] = (opps_d["first_signal_i"] - sig_m1).abs()
                nearest = opps_d.loc[opps_d["dist"].idxmin()]
                if nearest["dist"] <= match_window * 2:
                    if sig_m1 < nearest["first_signal_i"]:
                        classification = "5M_EARLIER"
                    else:
                        classification = "1M_EARLIER"
                    matched_opp = nearest["opportunity_id"]

        # Direction disagreement check
        opp_other = opp_by_dir.get("SHORT" if d == "LONG" else "LONG", pd.DataFrame())
        disagree = pd.DataFrame()
        if not opp_other.empty:
            disagree = opp_other[
                (opp_other["first_signal_i"] <= sig_m1 + disagree_window)
                & (opp_other["last_signal_i"] >= sig_m1 - disagree_window)
            ]
        if not disagree.empty and classification in ("5M_ONLY", "5M_EARLIER", "1M_EARLIER"):
            classification = "DIRECTION_DISAGREEMENT"

        rows.append({
            "setup_id": sid,
            "5m_take_j": take_j,
            "5m_arm_j": arm_j,
            "direction": d,
            "5m_take_m1_i": sig_m1,
            "5m_arm_m1_i": arm_m1,
            "5m_take_price": tk["take_price"],
            "5m_take_ts": tk.get("take_ts", ""),
            "5m_arm_ts": setup.get("armed_ts", ""),
            "matched_opportunity_id": matched_opp,
            "classification": classification,
        })
    return pd.DataFrame(rows)


def classify_1m_only(opps_1m: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Mark 1M opportunities not matched by any 5M TAKE."""
    matched = set(matches.loc[matches["classification"] == "SAME_OPPORTUNITY", "matched_opportunity_id"])
    also = set(matches.loc[matches["classification"].isin(["5M_EARLIER", "1M_EARLIER", "AMBIGUOUS_MATCH"]), "matched_opportunity_id"])
    matched |= also
    opps = opps_1m.copy()
    opps["5m_match"] = np.where(opps["opportunity_id"].isin(matched), "MATCHED", "1M_ONLY")
    return opps
