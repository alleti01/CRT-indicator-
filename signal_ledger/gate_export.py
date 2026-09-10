"""Parse TradingView chart data exports with GLD_* gate instrumentation plots."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from signal_ledger.config import GATE_NAMES, GLD_OPTIONAL_COLS, NULLABLE_GATE_NAMES

GLD_PREFIX = "GLD_"
UTC_MS_COL = "GLD_bar_time_utc_ms"
PIVOT_LAG_COLS = ("GLD_pivot_high_center_lag", "GLD_pivot_low_center_lag", "GLD_swing_period")


def _normalize_col(name: str) -> str:
    s = str(name).strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s


def _find_gld_columns(columns: list[str]) -> dict[str, str]:
    norm = {_normalize_col(c): c for c in columns}
    out: dict[str, str] = {}
    for gate in GATE_NAMES:
        plot = f"{GLD_PREFIX}{gate}"
        if plot in norm:
            out[gate] = norm[plot]
        else:
            for nk, raw in norm.items():
                if nk.replace(" ", "_").lower() == plot.lower():
                    out[gate] = raw
                    break
    return out


def _parse_utc_series(df: pd.DataFrame) -> pd.Series:
    if UTC_MS_COL in df.columns:
        ms = pd.to_numeric(df[UTC_MS_COL], errors="coerce")
        return pd.to_datetime(ms, unit="ms", utc=True)
    for col in ("time", "Time", "date", "Date"):
        if col in df.columns:
            v = df[col]
            if pd.api.types.is_numeric_dtype(v):
                unit = "ms" if float(v.dropna().iloc[0]) > 1e12 else "s"
                return pd.to_datetime(v, unit=unit, utc=True)
            return pd.to_datetime(v, utc=True)
    raise ValueError("No UTC timestamp column found (need GLD_bar_time_utc_ms or time)")


def _as_bool(series: pd.Series) -> pd.Series:
    v = pd.to_numeric(series, errors="coerce")
    return v.fillna(0) > 0.5


def _as_bool_nullable(series: pd.Series) -> pd.Series:
    """Preserve na — Part D: never map export na to False for evidence gates."""
    v = pd.to_numeric(series, errors="coerce")
    out = pd.Series([pd.NA] * len(v), dtype="boolean")
    mask = v.notna()
    out.loc[mask] = v.loc[mask] > 0.5
    return out


def load_tv_gate_export(path: Path | str) -> pd.DataFrame:
    """
    Load a TradingView chart export CSV with GLD_* data-window plots.

    evidence_threshold_* columns use nullable boolean (na preserved).
    """
    path = Path(path)
    raw = pd.read_csv(path)
    raw.columns = [_normalize_col(c) for c in raw.columns]

    bar_time = _parse_utc_series(raw).dt.floor("min")
    gld_map = _find_gld_columns(list(raw.columns))
    missing = [g for g in GATE_NAMES if g not in gld_map]
    if missing:
        raise ValueError(f"Gate export missing GLD columns for: {missing}")

    out = pd.DataFrame({"bar_time_utc": bar_time})
    for gate, col in gld_map.items():
        if gate in NULLABLE_GATE_NAMES:
            out[gate] = _as_bool_nullable(raw[col])
        else:
            out[gate] = _as_bool(raw[col])

    for pc in PIVOT_LAG_COLS:
        if pc in raw.columns:
            out[pc.replace(GLD_PREFIX, "").lower()] = pd.to_numeric(raw[pc], errors="coerce")

    for col in GLD_OPTIONAL_COLS:
        plot = f"{GLD_PREFIX}{col}"
        if plot in raw.columns:
            if col == "htf_warmup_ready":
                out[col] = _as_bool(raw[plot])
            else:
                out[col] = pd.to_numeric(raw[plot], errors="coerce")

    out = out.drop_duplicates(subset=["bar_time_utc"], keep="last")
    return out.sort_values("bar_time_utc").reset_index(drop=True)


def export_row_at_time(gates_df: pd.DataFrame, bar_time_utc: pd.Timestamp) -> pd.Series | None:
    key = pd.Timestamp(bar_time_utc).tz_convert("UTC").floor("min")
    hit = gates_df[gates_df["bar_time_utc"] == key]
    if hit.empty:
        return None
    return hit.iloc[-1]
