"""Paper position tracking — incremental stop/target/time exits."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from phase45.execution.data_1m import cost_r
from phase53.config import MAX_HOLD_MIN, STOP_ATR, TARGET_R


@dataclass
class OpenPosition:
    signal_id: str
    episode_id: str
    direction: str
    entry_i: int
    entry_timestamp: pd.Timestamp
    entry_price: float
    atr: float
    stop: float
    target: float
    time_exit_deadline: pd.Timestamp
    core_authorized: int
    mfe: float = 0.0
    mae: float = 0.0

    def to_json(self) -> dict:
        return {
            "state": "OPEN",
            "signal_id": self.signal_id,
            "episode_id": self.episode_id,
            "direction": self.direction,
            "entry_i": self.entry_i,
            "entry_timestamp": str(self.entry_timestamp),
            "entry_price": self.entry_price,
            "atr": self.atr,
            "stop": self.stop,
            "target": self.target,
            "time_exit_deadline": str(self.time_exit_deadline),
            "core_authorized": self.core_authorized,
            "current_MFE": self.mfe,
            "current_MAE": self.mae,
        }


@dataclass
class PaperTradeManager:
    m1: pd.DataFrame
    position: OpenPosition | None = None
    closed: list[dict] = field(default_factory=list)

    def is_flat(self) -> bool:
        return self.position is None

    def open_from_signal(self, sig: dict) -> None:
        i = int(sig["entry_i"])
        atr = float(sig["atr"])
        d = sig["direction"]
        ep = float(sig["entry_price"])
        risk = STOP_ATR * atr
        stop = ep - risk if d == "LONG" else ep + risk
        target = ep + TARGET_R * risk if d == "LONG" else ep - TARGET_R * risk
        deadline_i = min(len(self.m1) - 1, i + MAX_HOLD_MIN)
        self.position = OpenPosition(
            signal_id=sig["signal_id"],
            episode_id=sig["episode_id"],
            direction=d,
            entry_i=i,
            entry_timestamp=pd.Timestamp(sig["entry_timestamp"]),
            entry_price=ep,
            atr=atr,
            stop=stop,
            target=target,
            time_exit_deadline=self.m1.index[deadline_i],
            core_authorized=int(sig.get("core_authorized", 0)),
        )

    def update_bar(self, i: int) -> dict | None:
        if self.position is None or i <= self.position.entry_i:
            return None
        pos = self.position
        hi = float(self.m1["high"].iloc[i])
        lo = float(self.m1["low"].iloc[i])
        cl = float(self.m1["close"].iloc[i])
        ep = pos.entry_price
        risk = STOP_ATR * pos.atr
        d = 1 if pos.direction == "LONG" else -1
        if d == 1:
            pos.mfe = max(pos.mfe, (hi - ep) / risk)
            pos.mae = max(pos.mae, (ep - lo) / risk)
            hit_stop = lo <= pos.stop
            hit_tgt = hi >= pos.target
        else:
            pos.mfe = max(pos.mfe, (ep - lo) / risk)
            pos.mae = max(pos.mae, (hi - ep) / risk)
            hit_stop = hi >= pos.stop
            hit_tgt = lo <= pos.target
        exit_price = cl
        exit_reason = "TIME"
        gross_r = (cl - ep) / risk * d
        if hit_stop:
            exit_price, exit_reason, gross_r = pos.stop, "STOP", -1.0
        elif hit_tgt:
            exit_price, exit_reason, gross_r = pos.target, "TARGET", TARGET_R
        elif pd.Timestamp(self.m1.index[i]) >= pos.time_exit_deadline:
            exit_price, exit_reason = cl, "TIME"
            gross_r = (cl - ep) / risk * d
        else:
            return None
        cr = cost_r(ep, pos.stop, 1.0)
        trade = {
            "signal_id": pos.signal_id,
            "episode_id": pos.episode_id,
            "direction": pos.direction,
            "entry_timestamp": pos.entry_timestamp,
            "entry_price": ep,
            "exit_timestamp": self.m1.index[i],
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "gross_R": gross_r,
            "cost_R": cr,
            "net_R": gross_r - cr,
            "MFE_R": pos.mfe,
            "MAE_R": pos.mae,
            "duration_minutes": (pd.Timestamp(self.m1.index[i]) - pos.entry_timestamp).total_seconds() / 60.0,
            "core_authorized": pos.core_authorized,
        }
        self.closed.append(trade)
        self.position = None
        return trade

    def open_position_json(self) -> dict:
        if self.position is None:
            return {"state": "FLAT"}
        return self.position.to_json()

    def reconstruct_from_trades(self, open_trade: dict | None) -> None:
        if not open_trade:
            self.position = None
            return
        self.position = OpenPosition(
            signal_id=open_trade["signal_id"],
            episode_id=open_trade["episode_id"],
            direction=open_trade["direction"],
            entry_i=int(open_trade["entry_i"]),
            entry_timestamp=pd.Timestamp(open_trade["entry_timestamp"]),
            entry_price=float(open_trade["entry_price"]),
            atr=float(open_trade["atr"]),
            stop=float(open_trade["stop"]),
            target=float(open_trade["target"]),
            time_exit_deadline=pd.Timestamp(open_trade["time_exit_deadline"]),
            core_authorized=int(open_trade.get("core_authorized", 0)),
            mfe=float(open_trade.get("current_MFE", 0)),
            mae=float(open_trade.get("current_MAE", 0)),
        )
