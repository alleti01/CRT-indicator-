"""Phase72A signal provenance — strict source hierarchy."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from phase84.python.config import (
    LEDGER_EXPORT_PATH,
    PROVISIONAL_MIRROR_FLAG,
    TV_EXPORT_PATH,
    WEBHOOK_CSV,
)


REQUIRED_COLS = (
    "phase72a_event_id",
    "phase72a_signal_time",
    "phase72a_direction",
    "phase72a_source",
    "signal_i",
    "entry_i",
)


def _normalize_direction(event: str) -> str:
    if "LONG" in event.upper():
        return "LONG"
    if "SHORT" in event.upper():
        return "SHORT"
    raise ValueError(f"Unknown direction event: {event}")


def load_tv_export(path: Path = TV_EXPORT_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(REQUIRED_COLS))
    df = pd.read_csv(path)
    df["phase72a_signal_time"] = pd.to_datetime(df["signal_time"], utc=True)
    df["phase72a_direction"] = df["direction"].str.upper()
    df["phase72a_event_id"] = df.get("event_id", df.index.astype(str))
    df["phase72a_source"] = "REAL_TV_EXPORT"
    return df


def load_ledger_export(path: Path = LEDGER_EXPORT_PATH) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(REQUIRED_COLS))
    df = pd.read_csv(path)
    df["phase72a_signal_time"] = pd.to_datetime(df["signal_time"], utc=True)
    df["phase72a_direction"] = df["direction"].str.upper()
    df["phase72a_event_id"] = df.get("event_id", df.index.astype(str))
    df["phase72a_source"] = "REAL_LEDGER_EXPORT"
    return df


def load_webhook_log(path: Path = WEBHOOK_CSV) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(REQUIRED_COLS))
    raw = pd.read_csv(path)
    acc = raw.loc[raw["outcome"] == "ACCEPTED"].copy()
    if acc.empty:
        return pd.DataFrame(columns=list(REQUIRED_COLS))
    acc["phase72a_signal_time"] = pd.to_datetime(acc["signal_bar_time_utc"], utc=True)
    acc["phase72a_direction"] = acc["event"].map(_normalize_direction)
    acc["phase72a_event_id"] = acc["signal_id"].astype(str) + "_" + acc["signal_bar_time_utc"].astype(str)
    acc["phase72a_source"] = "REAL_WEBHOOK_LOG"
    acc["signal_price"] = pd.to_numeric(acc["signal_price"], errors="coerce")
    return acc.reset_index(drop=True)


def load_provisional_mirror() -> pd.DataFrame:
    """Phase72B/Phase60 mirror — PROVISIONAL ONLY. Not Phase72A ground truth."""
    if not PROVISIONAL_MIRROR_FLAG:
        return pd.DataFrame(columns=list(REQUIRED_COLS))
    from phase69.python.entry_freeze import load_frozen_entries

    df = load_frozen_entries()
    out = pd.DataFrame({
        "phase72a_event_id": df["trade_id"],
        "phase72a_signal_time": pd.to_datetime(df["entry_ts"], utc=True) - pd.Timedelta(minutes=1),
        "phase72a_direction": df["direction"],
        "phase72a_source": "MIRROR_PROVISIONAL",
        "signal_i": df["signal_i"].astype(int),
        "entry_i": df["entry_i"].astype(int),
        "entry_price": df["entry_price"].astype(float),
        "atr_signal": df["atr_entry"].astype(float),
    })
    return out


def align_signals_to_market(
    signals: pd.DataFrame,
    m1_index: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, dict]:
    """Map signal times to bar indices (causal: signal at bar close T, entry T+1)."""
    meta: dict = {"input_n": int(len(signals)), "aligned_n": 0, "unaligned_reasons": {}}
    if signals.empty:
        return signals, meta
    idx = m1_index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    out = signals.copy()
    if "signal_i" not in out.columns or out["signal_i"].isna().all():
        locs = idx.get_indexer(out["phase72a_signal_time"], method="pad")
        out["signal_i"] = locs
        out.loc[locs < 0, "signal_i"] = pd.NA
        after_end = out["phase72a_signal_time"] > idx[-1]
        before_start = out["phase72a_signal_time"] < idx[0]
        meta["unaligned_reasons"]["after_m1_end"] = int(after_end.sum())
        meta["unaligned_reasons"]["before_m1_start"] = int(before_start.sum())
        meta["m1_range"] = f"{idx[0]} .. {idx[-1]}"
        if len(out):
            meta["signal_range"] = (
                f"{out['phase72a_signal_time'].min()} .. {out['phase72a_signal_time'].max()}"
            )
    if "entry_i" not in out.columns or out["entry_i"].isna().all():
        out["entry_i"] = out["signal_i"] + 1
    out = out.dropna(subset=["signal_i", "entry_i"]).copy()
    if out.empty:
        meta["aligned_n"] = 0
        return out, meta
    out["signal_i"] = out["signal_i"].astype(int)
    out["entry_i"] = out["entry_i"].astype(int)
    out = out.loc[(out["entry_i"] > out["signal_i"]) & (out["entry_i"] < len(idx))].copy()
    meta["aligned_n"] = int(len(out))
    return out.reset_index(drop=True), meta


def load_all_signals(m1_index: pd.DatetimeIndex | None = None) -> tuple[pd.DataFrame, dict]:
    """Load signals by provenance priority; never silently mix without tagging."""
    parts: list[pd.DataFrame] = []
    meta: dict = {}

    for name, loader in [
        ("REAL_TV_EXPORT", lambda: load_tv_export()),
        ("REAL_LEDGER_EXPORT", lambda: load_ledger_export()),
        ("REAL_WEBHOOK_LOG", lambda: load_webhook_log()),
        ("MIRROR_PROVISIONAL", lambda: load_provisional_mirror()),
    ]:
        df = loader()
        meta[name] = int(len(df))
        if not df.empty:
            parts.append(df)

    if not parts:
        combined = pd.DataFrame(columns=list(REQUIRED_COLS))
    else:
        combined = pd.concat(parts, ignore_index=True)
        combined = combined.sort_values("phase72a_signal_time").reset_index(drop=True)
        combined = combined.drop_duplicates("phase72a_event_id", keep="first")

    align_meta: dict = {}
    if m1_index is not None and not combined.empty:
        combined, align_meta = align_signals_to_market(combined, m1_index)
        meta["alignment"] = align_meta

    real_n = int((combined["phase72a_source"].isin([
        "REAL_TV_EXPORT", "REAL_LEDGER_EXPORT", "REAL_WEBHOOK_LOG"
    ])).sum()) if not combined.empty else 0

    meta["total"] = int(len(combined))
    meta["real_count"] = real_n
    meta["provisional_count"] = int(len(combined)) - real_n
    meta["has_real_stream"] = real_n >= 500
    return combined, meta


def provenance_report(meta: dict) -> str:
    lines = [
        "# Phase84 Signal Provenance",
        "",
        f"- REAL_TV_EXPORT: {meta.get('REAL_TV_EXPORT', 0)}",
        f"- REAL_LEDGER_EXPORT: {meta.get('REAL_LEDGER_EXPORT', 0)}",
        f"- REAL_WEBHOOK_LOG: {meta.get('REAL_WEBHOOK_LOG', 0)}",
        f"- MIRROR_PROVISIONAL: {meta.get('MIRROR_PROVISIONAL', 0)}",
        f"- Total aligned: {meta.get('total', 0)}",
        f"- Real count: {meta.get('real_count', 0)}",
        f"- Has real stream (>=500): {meta.get('has_real_stream', False)}",
        "",
        "Phase72B / Phase60 mirror is disabled by default (`PROVISIONAL_MIRROR_FLAG=False`).",
    ]
    al = meta.get("alignment", {})
    if al:
        lines.extend([
            "",
            "## Alignment",
            f"- Input signals: {al.get('input_n', 0)}",
            f"- Aligned to M1: {al.get('aligned_n', 0)}",
            f"- M1 range: {al.get('m1_range', 'n/a')}",
            f"- Signal range: {al.get('signal_range', 'n/a')}",
            f"- Unaligned (after M1 end): {al.get('unaligned_reasons', {}).get('after_m1_end', 0)}",
            f"- Unaligned (before M1 start): {al.get('unaligned_reasons', {}).get('before_m1_start', 0)}",
        ])
    return "\n".join(lines)
