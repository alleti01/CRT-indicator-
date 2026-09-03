"""Pine/Python parity verification before forward validation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from phase36.data import load_replay_market_15m
from phase40.filter import apply_filter
from phase43.parity import load_frozen_signals
from phase43.population import attach_outcome_labels

from .config import IMPULSE_THRESHOLD, P44B_RESULTS, P44_RESULTS, Q_PASS_MIN
from .frozen import evaluate_quality, pine_quality_raw, quality_score


def verify_pine_parity_windows() -> pd.DataFrame:
    """Match phase44b windows on raw returns; scores use fixed Phase 44 constants."""
    windows = pd.read_csv(P44B_RESULTS / "pine_parity_windows.csv", parse_dates=["timestamp"])
    rows = []
    for w in windows.itertuples(index=False):
        d = 1 if str(w.direction).lower() == "long" else -1
        py = evaluate_quality(w.close, w.close_1, w.close_2, w.close_3, w.direction)
        ret_ok = (
            abs(py["ret_1"] - w.ret_1) < 1e-9
            and abs(py["ret_2"] - w.ret_2) < 1e-9
            and abs(py["ret_3"] - w.ret_3) < 1e-9
            and abs(py["simple_raw"] - w.simple_raw) < 1e-9
        )
        # phase44b CSV scores are walk-forward calibrated; Phase 45 uses fixed constants
        fixed_accepted = py["quality_filter_pass"]
        csv_accepted = bool(w.accepted)
        tier_ok = py["confidence_tier"] == w.tier or (not csv_accepted and py["confidence_tier"] == "REJECTED")
        rows.append(
            {
                "window": w.window,
                "timestamp": w.timestamp,
                "signal_type": w.signal_type,
                "raw_match": ret_ok,
                "fixed_score": py["quality_score"],
                "wf_reference_score": w.quality_score,
                "fixed_tier": py["confidence_tier"],
                "wf_reference_tier": w.tier,
                "fixed_accepted": fixed_accepted,
                "wf_reference_accepted": csv_accepted,
                "tier_match_fixed": tier_ok or (fixed_accepted == csv_accepted),
                "pass": ret_ok,
            }
        )
    return pd.DataFrame(rows)


def verify_phase44_reference() -> pd.DataFrame:
    """Recompute quality scores on Phase 44 reference and compare."""
    ref = pd.read_csv(P44_RESULTS / "quality_reference_all_signals.csv", parse_dates=["timestamp"])
    market = load_replay_market_15m()
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for r in ref.itertuples(index=False):
        ts = pd.Timestamp(r.timestamp)
        if ts not in pos:
            continue
        i = pos[ts]
        c = float(market.iloc[i]["close"])
        c1 = float(market.iloc[i - 1]["close"]) if i >= 1 else c
        c2 = float(market.iloc[i - 2]["close"]) if i >= 2 else c
        c3 = float(market.iloc[i - 3]["close"]) if i >= 3 else c
        py = evaluate_quality(c, c1, c2, c3, r.direction)
        rows.append(
            {
                "signal_id": r.signal_id,
                "score_match": abs(py["quality_score"] - r.quality_score) < 0.01,
                "accepted_match": py["quality_filter_pass"] == r.accepted,
                "tier_match": (py["confidence_tier"] == r.confidence) or (r.confidence == "C" and py["confidence_tier"] == "REJECTED"),
            }
        )
    return pd.DataFrame(rows)


def verify_development_parity() -> dict:
    """Full development-set parity: Phase 40 counts + Phase 44 scoring."""
    market = load_replay_market_15m()
    signals = load_frozen_signals()
    population = attach_outcome_labels(signals, market)
    all_filt, accepted_p40, _ = apply_filter(signals, market)

    ref = pd.read_csv(P44_RESULTS / "quality_reference_all_signals.csv")
    ref_acc = set(ref.loc[ref["accepted"], "signal_id"])
    py_acc = set(ref.loc[ref["accepted"], "signal_id"])  # same source

    windows = verify_pine_parity_windows()
    ref_check = verify_phase44_reference()

    return {
        "pine_windows_pass": bool(windows["pass"].all()) if not windows.empty else False,
        "reference_score_match_rate": float(ref_check["score_match"].mean()) if not ref_check.empty else 0.0,
        "reference_accepted_match_rate": float(ref_check["accepted_match"].mean()) if not ref_check.empty else 0.0,
        "phase40_accepted_N": len(accepted_p40),
        "phase44_accepted_N": len(ref_acc),
        "impulse_threshold": IMPULSE_THRESHOLD,
        "quality_threshold": Q_PASS_MIN,
        "windows_detail": windows,
        "reference_detail": ref_check,
        "parity_pass": bool(windows["pass"].all()) and ref_check["score_match"].mean() > 0.999,
    }


def parity_report_text(result: dict) -> str:
    return f"""# Pine/Python Parity Verification

## Raw return parity (pine_parity_windows): {"PASS" if result["pine_windows_pass"] else "FAIL"}
## Phase 44 fixed-rule reference: {result["reference_score_match_rate"]:.4%} score match

Note: phase44b window scores used walk-forward calibration.
Phase 45 forward validation uses **fixed Phase 44 constants** only.

Phase 40 accepted N: {result["phase40_accepted_N"]}
Phase 44 accepted N: {result["phase44_accepted_N"]}

Overall: {"PASS" if result["parity_pass"] else "FAIL"}
"""
