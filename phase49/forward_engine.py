"""Forward B1 + M0 engine on frozen Phase44 signals."""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np
import pandas as pd

from phase36.data import load_replay_market_15m
from phase45.execution.confirm import confirm_b1
from phase45.execution.data_1m import load_market_1m
from phase45.execution.simulate import simulate_1m
from phase45.forward import build_forward_log

from .config import (
    DATASET_TAG_FORWARD,
    DEVELOPMENT_CUTOFF,
    FORWARD_START_TIMESTAMP,
    FROZEN_B1_WINDOW_MIN,
    TIMEZONE,
)


def frozen_cutoff() -> pd.Timestamp:
    return pd.Timestamp(DEVELOPMENT_CUTOFF, tz=TIMEZONE)


def frozen_forward_start() -> pd.Timestamp:
    return pd.Timestamp(FORWARD_START_TIMESTAMP, tz=TIMEZONE)


def build_phase44_forward_signals(market_15m: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    mkt = market_15m if market_15m is not None else load_replay_market_15m()
    cutoff = frozen_cutoff()
    log, meta = build_forward_log(mkt, cutoff=cutoff)
    meta["forward_start_frozen"] = str(frozen_forward_start())
    meta["development_cutoff_frozen"] = str(cutoff)
    return log, meta


def _ensure_signal_ids(log: pd.DataFrame) -> pd.DataFrame:
    df = log.copy()
    if "signal_id" not in df.columns or df["signal_id"].isna().any():
        df["signal_id"] = [f"FWD-{i:05d}" for i in range(len(df))]
    return df


def process_forward_b1_m0(
    phase44_log: pd.DataFrame,
    market_1m: pd.DataFrame | None = None,
    *,
    model_hash: str = "",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply frozen B1 + M0 to forward Phase44 accepted signals."""
    mkt = market_1m if market_1m is not None else load_market_1m()
    pos = {ts: i for i, ts in enumerate(mkt.index)}
    tz = mkt.index.tz

    sig_rows: list[dict] = []
    trade_rows: list[dict] = []

    for _, sig in _ensure_signal_ids(phase44_log).iterrows():
        sid = sig["signal_id"]
        p44_ts = pd.Timestamp(sig["timestamp"]).tz_convert(TIMEZONE)
        direction = sig["direction"]
        st = sig["signal_type"]
        tier = sig.get("confidence_tier", sig.get("confidence", ""))
        score = sig.get("quality_score", np.nan)
        accepted = bool(sig.get("accepted", False))

        act = p44_ts + pd.Timedelta(minutes=15)
        act = act.tz_convert(tz)

        b1_confirmed = False
        b1_time = pd.NaT
        b1_delay = np.nan
        filled = False
        entry_time = pd.NaT
        entry_price = np.nan
        unfilled_reason = ""

        if not accepted:
            unfilled_reason = str(sig.get("rejection_reason", "PHASE44_REJECTED"))
        else:
            fill = confirm_b1(mkt, pos, act, FROZEN_B1_WINDOW_MIN, direction)
            b1_confirmed = fill.filled
            if fill.filled:
                b1_time = fill.entry_time
                b1_delay = fill.delay_min
                filled = True
                entry_time = fill.entry_time
                entry_price = fill.entry_price
            else:
                unfilled_reason = "B1_NOT_CONFIRMED"

        sig_rows.append({
            "signal_id": sid,
            "phase44_time": p44_ts,
            "direction": direction,
            "phase44_class": tier,
            "setup_type": st,
            "score": score,
            "b1_window": FROZEN_B1_WINDOW_MIN,
            "b1_confirmed": int(b1_confirmed),
            "b1_time": b1_time,
            "b1_delay": b1_delay,
            "filled": int(filled),
            "entry_time": entry_time,
            "entry_price": entry_price,
            "unfilled_reason": unfilled_reason,
            "model_hash": model_hash,
            "dataset_tag": DATASET_TAG_FORWARD,
            "stop": sig.get("stop"),
            "target": sig.get("target"),
        })

        if filled:
            ei = pos.get(entry_time, int(mkt.index.searchsorted(entry_time, side="left")))
            sim = simulate_1m(
                mkt, ei, float(entry_price), float(sig["stop"]), float(sig["target"]),
                direction, st,
            )
            risk = abs(float(entry_price) - float(sig["stop"]))
            trade_rows.append({
                "trade_id": f"T-{sid}",
                "signal_id": sid,
                "timestamp": p44_ts,
                "direction": direction,
                "phase44_class": tier,
                "setup_type": st,
                "b1_window": FROZEN_B1_WINDOW_MIN,
                "b1_delay": b1_delay,
                "entry_time": entry_time,
                "entry_price": entry_price,
                "stop": sig["stop"],
                "target": sig["target"],
                "risk_points": risk,
                "exit_time": sim["exit_timestamp"],
                "exit_price": np.nan,
                "exit_type": sim["exit_type"],
                "gross_r": sim["gross_R"],
                "cost_r": sim["cost_R"],
                "net_r": sim["net_R"],
                "mae_r": sim["MAE_R"],
                "mfe_r": sim["MFE_R"],
                "hold_minutes": sim.get("hold_bars", np.nan),
                "wrong_direction": sim["wrong_direction"],
                "model_hash": model_hash,
                "data_status": "OK",
                "dataset_tag": DATASET_TAG_FORWARD,
            })

    return pd.DataFrame(sig_rows), pd.DataFrame(trade_rows)


def decision_state(sig_row: pd.Series) -> str:
    if not sig_row.get("accepted", True) and pd.isna(sig_row.get("filled")):
        return "PHASE44 SETUP REJECTED"
    if not bool(sig_row.get("filled", 0)):
        if bool(sig_row.get("b1_confirmed", 0)):
            return "B1 CONFIRMED"
        return "WAITING FOR B1"
    return "TRADE EXITED" if sig_row.get("exit_type") else "B1 CONFIRMED"


def build_explanation(sig: pd.Series, trade: pd.Series | None = None) -> dict[str, Any]:
    action = "WAIT"
    if trade is not None and not pd.isna(trade.get("net_r")):
        action = "LONG" if str(sig["direction"]).lower() == "long" else "SHORT"
    elif bool(sig.get("filled", 0)):
        action = "LONG" if str(sig["direction"]).lower() == "long" else "SHORT"
    return {
        "Direction": action,
        "Phase44": "VALID" if bool(sig.get("filled", 0) or sig.get("b1_confirmed", 0)) else "WAIT",
        "Phase44_class": sig.get("phase44_class"),
        "Setup_type": sig.get("setup_type"),
        "B1": "Bullish Micro-BOS confirmed" if str(sig.get("direction", "")).lower() == "long" and sig.get("b1_confirmed") else (
            "Bearish Micro-BOS confirmed" if sig.get("b1_confirmed") else "Pending"
        ),
        "Phase44_signal_time": str(sig.get("phase44_time", "")),
        "B1_time": str(sig.get("b1_time", "")),
        "Entry_delay_min": sig.get("b1_delay"),
        "Entry": sig.get("entry_price"),
        "Stop": sig.get("stop"),
        "Target": sig.get("target"),
        "Status": f"{action} CONFIRMED" if action in ("LONG", "SHORT") else "WAIT",
    }
