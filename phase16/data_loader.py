"""CSV ingestion and market-data validation."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd


PRICE_COLUMNS = ("open", "high", "low", "close")
REQUIRED_COLUMNS = (*PRICE_COLUMNS, "volume")

ALIASES = {
    "timestamp": {"timestamp", "datetime", "date_time", "ts"},
    "open": {"open", "o"},
    "high": {"high", "h"},
    "low": {"low", "l"},
    "close": {"close", "c", "last"},
    "volume": {"volume", "vol", "v"},
    "contract": {"contract", "symbol", "instrument", "raw_symbol"},
}


class MarketDataError(ValueError):
    pass


def _normalized_name(name: object) -> str:
    return str(name).strip().lower().replace(" ", "_").replace("-", "_")


def _rename_columns(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = {_normalized_name(column): column for column in frame.columns}
    rename = {}
    for canonical, names in ALIASES.items():
        for alias in names:
            if alias in normalized:
                rename[normalized[alias]] = canonical
                break
    result = frame.rename(columns=rename)
    if "timestamp" not in result.columns:
        date_column = normalized.get("date")
        time_column = normalized.get("time")
        if date_column is not None and time_column is not None:
            result["timestamp"] = (
                result[date_column].astype(str).str.strip()
                + " "
                + result[time_column].astype(str).str.strip()
            )
        elif date_column is not None:
            result["timestamp"] = result[date_column]
    return result


def normalize_ohlcv(
    frame: pd.DataFrame,
    *,
    source_timezone: Optional[str] = None,
    exchange_timezone: str = "America/Chicago",
) -> pd.DataFrame:
    """Normalize and validate an OHLCV DataFrame.

    Naive timestamps are interpreted in ``source_timezone`` when provided and
    otherwise in the exchange timezone. Duplicate timestamp/contract rows keep
    the last observation, mirroring a corrected vendor record.
    """
    result = _rename_columns(frame.copy())
    missing = [column for column in ("timestamp", *REQUIRED_COLUMNS) if column not in result]
    if missing:
        raise MarketDataError(f"missing required columns: {', '.join(missing)}")

    parsed = pd.to_datetime(result["timestamp"], errors="coerce", utc=False)
    if parsed.isna().any():
        bad = int(parsed.isna().sum())
        raise MarketDataError(f"{bad} timestamp values could not be parsed")
    timestamp_index = pd.DatetimeIndex(parsed)
    if timestamp_index.tz is None:
        timezone = source_timezone or exchange_timezone
        try:
            timestamp_index = timestamp_index.tz_localize(
                timezone, ambiguous="infer", nonexistent="shift_forward"
            )
        except ValueError as exc:
            raise MarketDataError(f"cannot localize timestamps to {timezone}: {exc}") from exc
    timestamp_index = timestamp_index.tz_convert(exchange_timezone)
    result["timestamp"] = timestamp_index

    for column in REQUIRED_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    missing_values = result[list(REQUIRED_COLUMNS)].isna().sum()
    if int(missing_values.sum()) > 0:
        detail = ", ".join(
            f"{column}={int(count)}" for column, count in missing_values.items() if count
        )
        raise MarketDataError(f"missing/non-numeric OHLCV values: {detail}")

    subset = ["timestamp"] + (["contract"] if "contract" in result.columns else [])
    result = result.sort_values(subset).drop_duplicates(subset=subset, keep="last")
    if "contract" in result.columns:
        result["contract"] = result["contract"].astype(str).str.strip()
        if (result["contract"] == "").any():
            raise MarketDataError("contract contains blank values")

    high_floor = result[["open", "close", "low"]].max(axis=1)
    low_ceiling = result[["open", "close", "high"]].min(axis=1)
    invalid = (result["high"] < high_floor) | (result["low"] > low_ceiling)
    invalid |= result["high"] < result["low"]
    if invalid.any():
        first = result.loc[invalid, "timestamp"].iloc[0]
        raise MarketDataError(
            f"OHLC consistency failed on {int(invalid.sum())} rows; first at {first}"
        )
    if (result["volume"] < 0).any():
        raise MarketDataError("volume cannot be negative")

    keep = ["timestamp", *REQUIRED_COLUMNS]
    if "contract" in result.columns:
        keep.append("contract")
    # Databento continuous files expose the underlying roll through this field.
    if "instrument_id" in result.columns:
        keep.append("instrument_id")
    result = result[keep].set_index("timestamp").sort_index()
    if not result.index.is_monotonic_increasing:
        raise MarketDataError("timestamps are not ascending after normalization")
    return result


def load_ohlcv_csv(
    path: str | Path,
    *,
    source_timezone: Optional[str] = None,
    exchange_timezone: str = "America/Chicago",
) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    return normalize_ohlcv(
        pd.read_csv(path),
        source_timezone=source_timezone,
        exchange_timezone=exchange_timezone,
    )


def save_ohlcv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Save normalized data as CSV or parquet based on the extension."""
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    output = frame.reset_index()
    if destination.suffix.lower() in {".parquet", ".pq"}:
        try:
            output.to_parquet(destination, index=False)
        except ImportError as exc:
            raise RuntimeError("parquet output requires pyarrow") from exc
    else:
        output.to_csv(destination, index=False)
    return destination


def infer_bar_minutes(frame: pd.DataFrame) -> Optional[int]:
    if len(frame) < 2:
        return None
    differences = frame.index.to_series().diff().dropna().dt.total_seconds().div(60)
    differences = differences[differences > 0]
    if differences.empty:
        return None
    return int(round(float(differences.mode().iloc[0])))
