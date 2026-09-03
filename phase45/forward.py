"""Forward signal logger — chronological replay on post-cutoff data only."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd

from phase16.indicators import is_in_session
from phase16.resample import cme_session_date
from phase31.metrics import apply_costs
from phase37.concurrent import replay_concurrent
from phase40.filter import attach_entry_impulse
from phase39.classify import classify_dataframe
from phase39.paths import build_signal_paths

from .config import (
    DATASET_TAG,
    IMPULSE_THRESHOLD,
    MAX_HOLD_CONTINUATION_MIN,
    MAX_HOLD_REVERSAL_MIN,
    RTH_SESSION,
)
from .frozen import evaluate_quality


LOG_COLUMNS = [
    "signal_id", "timestamp", "session_date", "signal_type", "direction",
    "entry_candidate_price", "ATR", "impulse_3bar", "impulse_filter_pass",
    "ret_1", "ret_2", "ret_3", "simple_raw", "quality_score", "confidence_tier",
    "quality_filter_pass", "accepted", "rejection_reason", "entry", "stop", "target",
    "architecture", "dataset_tag",
]


def _empty_log() -> pd.DataFrame:
    return pd.DataFrame(columns=LOG_COLUMNS)


def development_cutoff(market: pd.DataFrame) -> pd.Timestamp:
    """Last bar in the research dataset — everything after is forward."""
    return pd.Timestamp(market.index[-1])


def score_forward_outcomes(signals: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Score hypothetical/actual outcomes with extended fields."""
    if signals.empty:
        return pd.DataFrame()
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for sig in signals.itertuples(index=False):
        ts = pd.Timestamp(sig.marker_bar_timestamp)
        if ts not in pos:
            continue
        entry_i = pos[ts]
        entry_px = float(sig.entry_price)
        stop = float(sig.stop)
        target = float(sig.target)
        st = str(sig.signal_type)
        direction = 1 if str(sig.direction).lower() == "long" else -1
        max_bars = 4 if st in ("L", "S") else 3
        max_hold_min = MAX_HOLD_CONTINUATION_MIN if st in ("L", "S") else MAX_HOLD_REVERSAL_MIN
        risk = abs(entry_px - stop) or 1e-9
        mfe = mae = 0.0
        bars_to_mfe = bars_to_mae = np.nan
        exit_type = "DATA_END"
        exit_ts = ts
        exit_px = entry_px
        realized_r = 0.0
        for elapsed, j in enumerate(range(entry_i + 1, len(market)), start=1):
            bar = market.iloc[j]
            hi, lo, close = float(bar.high), float(bar.low), float(bar.close)
            if direction == 1:
                bar_mfe = (hi - entry_px) / risk
                bar_mae = (entry_px - lo) / risk
                hit_stop = lo <= stop
                hit_tgt = hi >= target
            else:
                bar_mfe = (entry_px - lo) / risk
                bar_mae = (hi - entry_px) / risk
                hit_stop = hi >= stop
                hit_tgt = lo <= target
            if bar_mfe > mfe:
                mfe = bar_mfe
                bars_to_mfe = elapsed
            if bar_mae > mae:
                mae = bar_mae
                bars_to_mae = elapsed
            if hit_stop:
                exit_type, exit_ts, exit_px = "STOP", market.index[j], stop
                realized_r = (stop - entry_px) / risk if direction == 1 else (entry_px - stop) / risk
                break
            if hit_tgt:
                exit_type, exit_ts, exit_px = "TARGET", market.index[j], target
                realized_r = 3.0 if st in ("L", "S") else 2.5
                break
            if elapsed >= max_bars:
                exit_type, exit_ts, exit_px = "TIME", market.index[j], close
                realized_r = (close - entry_px) / risk if direction == 1 else (entry_px - close) / risk
                break
        gross = realized_r
        tmp = pd.DataFrame([{"entry_price": entry_px, "stop_price": stop, "realized_R": gross}])
        net = float(apply_costs(tmp, col="realized_R").iloc[0])
        cost = gross - net
        rows.append(
            {
                "signal_id": sig.signal_id,
                "exit_time": exit_ts,
                "exit_price": exit_px,
                "exit_reason": exit_type,
                "gross_R": gross,
                "cost_R": cost,
                "net_R": net,
                "MFE_R": mfe,
                "MAE_R": mae,
                "bars_to_MFE": bars_to_mfe,
                "bars_to_MAE": bars_to_mae,
                "max_hold_minutes": max_hold_min,
            }
        )
    return pd.DataFrame(rows)


def build_forward_log(market: pd.DataFrame, *, cutoff: pd.Timestamp | None = None) -> Tuple[pd.DataFrame, dict]:
    """
    Replay frozen strategy; log only signals strictly after development cutoff.

    Causal replay runs on full history; logging restricted to forward window.
    """
    cutoff = cutoff or development_cutoff(market)
    cutoff = pd.Timestamp(cutoff)

    raw_signals, _, _ = replay_concurrent(market)
    if raw_signals.empty:
        return _empty_log(), {"cutoff": cutoff, "forward_bars": 0, "total_candidates": 0}

    raw_signals = raw_signals.copy()
    raw_signals["marker_bar_timestamp"] = pd.to_datetime(raw_signals["timestamp_ct"], utc=True)

    # Phase 40 impulse layer on all replay signals
    p40 = attach_entry_impulse(raw_signals, market)

    # Restrict to forward-only timestamps
    forward_mask = p40["marker_bar_timestamp"] > cutoff
    forward = p40.loc[forward_mask].copy()

    pos = {ts: i for i, ts in enumerate(market.index)}
    log_rows = []
    for sig in forward.itertuples(index=False):
        ts = pd.Timestamp(sig.marker_bar_timestamp)
        i = pos[ts]
        bar = market.iloc[i]
        c = float(bar.close)
        c1 = float(market.iloc[i - 1]["close"]) if i >= 1 else c
        c2 = float(market.iloc[i - 2]["close"]) if i >= 2 else c
        c3 = float(market.iloc[i - 3]["close"]) if i >= 3 else c
        impulse_pass = bool(sig.accepted)
        q = evaluate_quality(c, c1, c2, c3, sig.direction) if impulse_pass else {
            "ret_1": np.nan, "ret_2": np.nan, "ret_3": np.nan,
            "simple_raw": np.nan, "quality_score": np.nan,
            "quality_filter_pass": False, "confidence_tier": "REJECTED",
        }
        if not impulse_pass:
            rejection = "IMPULSE_FILTER"
            final_accepted = False
        elif not q["quality_filter_pass"]:
            rejection = "QUALITY_FILTER"
            final_accepted = False
        else:
            rejection = ""
            final_accepted = True

        sess_date = cme_session_date(pd.DatetimeIndex([ts]))[0] if is_in_session(ts, RTH_SESSION) else None
        log_rows.append(
            {
                "signal_id": sig.signal_id,
                "timestamp": ts,
                "session_date": sess_date,
                "signal_type": sig.signal_type,
                "direction": sig.direction,
                "entry_candidate_price": float(sig.entry_price),
                "ATR": float(sig.atr),
                "impulse_3bar": float(sig.impulse_3bar),
                "impulse_filter_pass": impulse_pass,
                "ret_1": q["ret_1"],
                "ret_2": q["ret_2"],
                "ret_3": q["ret_3"],
                "simple_raw": q["simple_raw"],
                "quality_score": q["quality_score"],
                "confidence_tier": q["confidence_tier"],
                "quality_filter_pass": q["quality_filter_pass"] if impulse_pass else False,
                "accepted": final_accepted,
                "rejection_reason": rejection,
                "entry": float(sig.entry_price) if final_accepted else np.nan,
                "stop": float(sig.stop),
                "target": float(sig.target),
                "architecture": getattr(sig, "architecture", ""),
                "dataset_tag": DATASET_TAG,
            }
        )

    log = pd.DataFrame(log_rows)
    if log.empty:
        log = _empty_log()
        meta = {
            "cutoff": cutoff,
            "forward_start": cutoff + pd.Timedelta(minutes=15),
            "forward_bars": int((market.index > cutoff).sum()),
            "total_candidates": 0,
        }
        return log, meta

    outcomes = score_forward_outcomes(forward, market)
    paths = build_signal_paths(
        forward.assign(marker_bar_timestamp=forward["marker_bar_timestamp"]),
        market,
    )
    paths = classify_dataframe(paths)
    log = log.merge(outcomes, on="signal_id", how="left")
    if not paths.empty and "behavior_class" in paths.columns:
        log = log.merge(paths[["signal_id", "behavior_class"]], on="signal_id", how="left")
        log["wrong_direction_flag"] = (log["behavior_class"] == "WRONG_DIRECTION").astype(int)

    meta = {
        "cutoff": cutoff,
        "forward_start": log["timestamp"].min() if not log.empty else cutoff + pd.Timedelta(minutes=15),
        "forward_bars": int((market.index > cutoff).sum()),
        "total_candidates": len(log),
        "impulse_pass": int(log["impulse_filter_pass"].sum()),
        "quality_accepted": int(log["accepted"].sum()),
        "quality_rejected": int(log["impulse_filter_pass"].sum() - log["accepted"].sum()),
    }
    return log, meta


def current_signal_output(log: pd.DataFrame) -> dict | None:
    """Most recent accepted forward signal for live display."""
    if log.empty:
        return None
    acc = log.loc[log["accepted"]].sort_values("timestamp")
    if acc.empty:
        return None
    r = acc.iloc[-1]
    return {
        "TYPE": r["signal_type"],
        "CONFIDENCE": r["confidence_tier"],
        "QUALITY": round(float(r["quality_score"]), 1),
        "ENTRY": r["entry"],
        "STOP": r["stop"],
        "TARGET": r["target"],
        "MAX_HOLD": r.get("max_hold_minutes", MAX_HOLD_CONTINUATION_MIN if r["signal_type"] in ("L", "S") else MAX_HOLD_REVERSAL_MIN),
    }
