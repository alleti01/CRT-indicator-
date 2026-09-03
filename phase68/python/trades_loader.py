"""Phase68 — load and classify Databento trades."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from phase16.config import FrozenConfig

PILOT_TRADES = Path(__file__).resolve().parents[1] / "data" / "raw" / "nq_trades_pilot_202401.csv"
FALLBACK_TRADES = Path(__file__).resolve().parents[2] / "phase27" / "data" / "raw" / "nq_trades_pilot_202401.csv"


def trades_path() -> Path:
    if PILOT_TRADES.exists():
        return PILOT_TRADES
    return FALLBACK_TRADES


def load_trades(path: Path | None = None) -> pd.DataFrame:
    p = path or trades_path()
    df = pd.read_csv(p)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
    tz = FrozenConfig().exchange_timezone
    df["ts_local"] = df["timestamp"].dt.tz_convert(tz)
    df["price"] = df["price"].astype(float)
    df["size"] = df["size"].astype(float)
    df["is_buy"] = df["side"] == "B"
    df["is_sell"] = df["side"] == "A"
    df["is_unknown"] = df["side"] == "N"
    df["buy_vol"] = np.where(df["is_buy"], df["size"], 0.0)
    df["sell_vol"] = np.where(df["is_sell"], df["size"], 0.0)
    return df.sort_values("ts_local").reset_index(drop=True)


def classify_trades(df: pd.DataFrame) -> dict:
    n = len(df)
    buy = int(df["is_buy"].sum())
    sell = int(df["is_sell"].sum())
    unk = int(df["is_unknown"].sum())
    classified = buy + sell
    return {
        "n_trades": n,
        "buy_pct": buy / n if n else 0,
        "sell_pct": sell / n if n else 0,
        "unknown_pct": unk / n if n else 0,
        "method": "Databento exchange side field (B=buy aggressor, A=sell aggressor, N=unknown)",
        "confidence": "HIGH (exchange-reported aggressor)",
    }


def integrity_report(df: pd.DataFrame) -> dict:
    mono = df["ts_local"].is_monotonic_increasing
    dup = int(df["timestamp"].duplicated().sum())
    bad_price = int((df["price"] <= 0).sum())
    bad_size = int((df["size"] <= 0).sum())
    return {
        "monotonic": bool(mono),
        "duplicate_timestamps": dup,
        "bad_price": bad_price,
        "bad_size": bad_size,
        "start": str(df["ts_local"].min()),
        "end": str(df["ts_local"].max()),
        "pass": mono and bad_price == 0 and bad_size == 0,
    }
