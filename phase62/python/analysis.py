"""Phase62 — path ordering, forensics, profit states."""
from __future__ import annotations

import numpy as np
import pandas as pd


def path_ordering(m1_hi, m1_lo, m1_op, entry_i, direction, atr, max_h=60) -> dict:
    """Time to +/- thresholds; ordering probabilities."""
    ep = m1_op[entry_i]
    a = atr if atr > 0 else 1.0
    d = 1 if direction == "LONG" else -1
    end = min(entry_i + max_h, len(m1_hi))
    hs = m1_hi[entry_i:end]
    ls = m1_lo[entry_i:end]
    if d == 1:
        fav = (np.maximum.accumulate(hs) - ep) / a
        adv = (ep - np.minimum.accumulate(ls)) / a
    else:
        fav = (ep - np.minimum.accumulate(ls)) / a
        adv = (np.maximum.accumulate(hs) - ep) / a

    def _first_ge(arr, thr):
        hit = np.where(arr >= thr)[0]
        return int(hit[0] + 1) if len(hit) else None

    times = {}
    for thr in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
        times[f"+{thr}"] = _first_ge(fav, thr)
        times[f"-{thr}"] = _first_ge(adv, thr)

    def before(pos_thr, neg_thr):
        tp, tn = times.get(f"+{pos_thr}"), times.get(f"-{neg_thr}")
        if tp is None and tn is None:
            return None
        if tp is None:
            return False
        if tn is None:
            return True
        return tp < tn

    pairs = [
        ("+1_before_-1", before(1.0, 1.0)),
        ("+1.5_before_-1", before(1.5, 1.0)),
        ("+2_before_-1", before(2.0, 1.0)),
        ("+2.5_before_-1", before(2.5, 1.0)),
        ("+1_before_-1.5", before(1.0, 1.5)),
        ("+2_before_-1.5", before(2.0, 1.5)),
        ("+2.5_before_-1.5", before(2.5, 1.5)),
    ]
    return {"times": times, "pairs": dict(pairs)}


def aggregate_ordering(opps: pd.DataFrame, m1_hi, m1_lo, m1_op) -> dict:
    pair_counts = {}
    pair_totals = {}
    for direction in ("LONG", "SHORT", None):
        sub = opps if direction is None else opps[opps["direction"] == direction]
        key_prefix = "" if direction is None else f"{direction}_"
        for _, r in sub.iterrows():
            po = path_ordering(m1_hi, m1_lo, m1_op, int(r["entry_i"]), r["direction"], float(r["atr"]))
            for pname, val in po["pairs"].items():
                if val is None:
                    continue
                k = key_prefix + pname
                pair_totals[k] = pair_totals.get(k, 0) + 1
                if val:
                    pair_counts[k] = pair_counts.get(k, 0) + 1
    return {k: pair_counts.get(k, 0) / pair_totals[k] for k in pair_totals}


def profit_state_analysis(m1_hi, m1_lo, m1_op, m1_cl, opps: pd.DataFrame) -> dict:
    """Retrospective: after reaching +XR, what happens next."""
    states = [0.5, 1.0, 1.5, 2.0, 2.5]
    report = {}
    for thr in states:
        eventual_25 = []
        eventual_stop = []
        givebacks = []
        for _, r in opps.iterrows():
            ei = int(r["entry_i"])
            ep = m1_op[ei]
            a = float(r["atr"]) if r["atr"] > 0 else 1.0
            d = 1 if r["direction"] == "LONG" else -1
            risk = a  # normalized to 1R = 1 ATR for state study
            end = min(ei + 60, len(m1_cl))
            reached = False
            max_fav_after = 0.0
            min_after = 999.0
            for k in range(ei, end):
                hi, lo = m1_hi[k], m1_lo[k]
                fav = (hi - ep) * d / risk if d == 1 else (ep - lo) / risk
                adv = (ep - lo) / risk if d == 1 else (hi - ep) / risk
                if fav >= thr:
                    reached = True
                if reached:
                    max_fav_after = max(max_fav_after, fav)
                    cur = (m1_cl[k] - ep) * d / risk
                    min_after = min(min_after, cur)
            if reached:
                eventual_25.append(max_fav_after >= 2.5)
                eventual_stop.append(min_after <= -1.0)
                givebacks.append(max_fav_after - max(min_after, 0))
        n = len(eventual_25)
        report[f"after_{thr}R"] = {
            "n": n,
            "eventual_2.5R": float(np.mean(eventual_25)) if n else 0,
            "eventual_stop": float(np.mean(eventual_stop)) if n else 0,
            "median_giveback": float(np.median(givebacks)) if givebacks else 0,
        }
    return report


def bad_stop_forensics(m1_hi, m1_lo, m1_op, opps: pd.DataFrame) -> dict:
    """Classify stopped-then-recovered patterns (retrospective)."""
    cats = {"too_tight": 0, "bad_entry_recovery": 0, "structure_valid": 0, "ambiguous": 0}
    count = 0
    for _, r in opps.iterrows():
        ei = int(r["entry_i"])
        ep = m1_op[ei]
        a = float(r["atr"]) if r["atr"] > 0 else 1.0
        d = 1 if r["direction"] == "LONG" else -1
        stop = ep - d * a
        end = min(ei + 60, len(m1_hi))
        stopped_at = None
        mfe_before = 0.0
        mae_before = 0.0
        for k in range(ei, end):
            hi, lo = m1_hi[k], m1_lo[k]
            fav = (hi - ep) * d / a if d == 1 else (ep - lo) / a
            adv = (ep - lo) / a if d == 1 else (hi - ep) / a
            mfe_before = max(mfe_before, fav)
            mae_before = max(mae_before, adv)
            hit = lo <= stop if d == 1 else hi >= stop
            if hit:
                stopped_at = k
                break
        if stopped_at is None:
            continue
        count += 1
        # MFE after stop
        mfe_after = 0.0
        for k in range(stopped_at + 1, end):
            hi, lo = m1_hi[k], m1_lo[k]
            fav = (hi - ep) * d / a if d == 1 else (ep - lo) / a
            mfe_after = max(mfe_after, fav)
        if mfe_after >= 2.0 and mfe_before < 1.0:
            cats["too_tight"] += 1
        elif mfe_after >= 2.0 and mae_before > 1.5:
            cats["bad_entry_recovery"] += 1
        elif mfe_after >= 1.5 and mfe_before >= 0.5:
            cats["structure_valid"] += 1
        else:
            cats["ambiguous"] += 1
    total = max(1, count)
    return {"count": count, "pct": {k: v / total for k, v in cats.items()}}


def entry_judgment_masks(feat: pd.DataFrame) -> dict:
    """J1/J2/J3 soft judgment masks."""
    j1 = feat["chase_atr"] < 1.5  # not obvious chase
    j2 = feat["location_score"] >= 1  # not clearly poor location
    j3 = ~(
        ((feat["direction"] == "LONG") & (feat["m5_state"] == "BEARISH") & (feat["m15_state"] == "BEARISH"))
        | ((feat["direction"] == "SHORT") & (feat["m5_state"] == "BULLISH") & (feat["m15_state"] == "BULLISH"))
    )
    return {"J1_not_chased": j1, "J2_location_ok": j2, "J3_no_conflict": j3}
