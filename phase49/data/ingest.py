"""Append-safe forward NQ data ingestion for Phase 49."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from phase16.data_loader import load_ohlcv_csv, normalize_ohlcv
from phase16.indicators import pine_sma

from phase49.config import ROOT, TIMEZONE

from .firewall import (
    assert_forward_only,
    assert_no_overlap,
    development_cutoff_ts,
    forward_start_ts,
    split_development_forward,
)
from .paths import (
    BRIDGE_1M_SOURCES,
    DATA_DIR,
    FORWARD_15M_PROCESSED,
    FORWARD_1M_PROCESSED,
    FORWARD_5M_PROCESSED,
    FORWARD_DIR,
    FORWARD_MANIFEST,
    INBOUND_DIR,
    INBOUND_1M_GLOB,
)
from .resample import resample_1m_to_15m, resample_1m_to_5m


def _discover_raw_1m_paths() -> list[Path]:
    paths: list[Path] = []
    for source in BRIDGE_1M_SOURCES:
        if source.is_file():
            paths.append(source)
        elif source.is_dir():
            paths.extend(sorted(source.glob("*.csv")))
    if INBOUND_DIR.exists():
        paths.extend(sorted(INBOUND_DIR.glob(INBOUND_1M_GLOB)))
    return paths


def _load_raw_frames(paths: list[Path]) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for path in paths:
        if not path.exists():
            continue
        parts.append(load_ohlcv_csv(path, source_timezone="UTC"))
    if not parts:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return pd.concat(parts).sort_index()


def _dedupe_idempotent(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    dup_mask = df.index.duplicated(keep=False)
    if not dup_mask.any():
        return df[~df.index.duplicated(keep="last")]
    for ts in df.index[dup_mask].unique():
        rows = df.loc[[ts]]
        if len(rows) == 1:
            continue
        ref = rows.iloc[0][["open", "high", "low", "close", "volume"]].astype(float)
        for _, row in rows.iloc[1:].iterrows():
            cur = row[["open", "high", "low", "close", "volume"]].astype(float)
            if not ref.equals(cur):
                raise ValueError(f"conflicting OHLC at duplicate timestamp {ts}")
    return df[~df.index.duplicated(keep="last")]


def _attach_1m_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    atr = (out["high"] - out["low"]).rolling(14).mean()
    out["atr"] = atr
    vol_sma = pine_sma(out["volume"].astype(float), 20)
    out["rel_volume"] = out["volume"].astype(float) / vol_sma.replace(0, pd.NA)
    out["vol_ma5"] = out["volume"].astype(float).rolling(5).mean()
    return out


def _read_processed(path: Path) -> pd.DataFrame:
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    raw = pd.read_csv(path)
    if raw.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return load_ohlcv_csv(path, source_timezone=TIMEZONE)


def _write_processed(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if df.empty:
        pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"]).to_csv(path, index=False)
        return
    out = df.sort_index()
    out.reset_index().to_csv(path, index=False)


def _file_sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def ingest_forward_data(*, force: bool = False) -> dict[str, Any]:
    """Ingest inbound / bridge raw 1m sources into processed forward store."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FORWARD_DIR.mkdir(parents=True, exist_ok=True)
    INBOUND_DIR.mkdir(parents=True, exist_ok=True)

    raw_paths = _discover_raw_1m_paths()
    raw = _load_raw_frames(raw_paths)
    raw = _dedupe_idempotent(raw)

    _, forward_candidates = split_development_forward(raw)
    assert_forward_only(forward_candidates)

    existing = _read_processed(FORWARD_1M_PROCESSED)
    if not existing.empty:
        existing = existing[~existing.index.duplicated(keep="last")]
    merged = pd.concat([existing, forward_candidates]).sort_index()
    merged = _dedupe_idempotent(merged)
    assert_forward_only(merged)

    dev_bridge, _ = split_development_forward(raw)
    assert_no_overlap(dev_bridge, merged)

    if not force and not forward_candidates.empty and not existing.empty:
        if len(merged) == len(existing) and merged.index.equals(existing.index):
            pass  # idempotent no-op

    _write_processed(merged, FORWARD_1M_PROCESSED)

    bars_5m = resample_1m_to_5m(merged) if not merged.empty else merged.copy()
    bars_15m = resample_1m_to_15m(merged) if not merged.empty else merged.copy()
    _write_processed(bars_5m, FORWARD_5M_PROCESSED)
    _write_processed(bars_15m, FORWARD_15M_PROCESSED)

    manifest = write_forward_manifest(
        raw_paths=raw_paths,
        forward_1m=merged,
        forward_5m=bars_5m,
        forward_15m=bars_15m,
        bridge_rows=len(dev_bridge),
        new_forward_rows=len(forward_candidates),
    )
    return manifest


def write_forward_manifest(
    *,
    raw_paths: list[Path] | None = None,
    forward_1m: pd.DataFrame | None = None,
    forward_5m: pd.DataFrame | None = None,
    forward_15m: pd.DataFrame | None = None,
    bridge_rows: int = 0,
    new_forward_rows: int = 0,
) -> dict[str, Any]:
    raw_paths = raw_paths or _discover_raw_1m_paths()
    if forward_1m is None:
        forward_1m = _read_processed(FORWARD_1M_PROCESSED)
    if forward_5m is None:
        forward_5m = _read_processed(FORWARD_5M_PROCESSED)
    if forward_15m is None:
        forward_15m = _read_processed(FORWARD_15M_PROCESSED)

    manifest: dict[str, Any] = {
        "ingestion_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "timezone": TIMEZONE,
        "development_cutoff": str(development_cutoff_ts()),
        "forward_start": str(forward_start_ts()),
        "1m": {
            "sources": [str(p.relative_to(ROOT)) if str(p).startswith(str(ROOT)) else str(p) for p in raw_paths],
            "processed_path": str(FORWARD_1M_PROCESSED.relative_to(ROOT)),
            "first_timestamp": str(forward_1m.index.min()) if not forward_1m.empty else None,
            "last_timestamp": str(forward_1m.index.max()) if not forward_1m.empty else None,
            "row_count": len(forward_1m),
            "checksum_sha256": _file_sha256(FORWARD_1M_PROCESSED),
            "new_rows_ingested": new_forward_rows,
            "bridge_rows_seen": bridge_rows,
        },
        "5m": {
            "source": "derived_from_forward_1m",
            "processed_path": str(FORWARD_5M_PROCESSED.relative_to(ROOT)),
            "first_timestamp": str(forward_5m.index.min()) if not forward_5m.empty else None,
            "last_timestamp": str(forward_5m.index.max()) if not forward_5m.empty else None,
            "row_count": len(forward_5m),
            "checksum_sha256": _file_sha256(FORWARD_5M_PROCESSED),
        },
        "15m": {
            "source": "derived_from_forward_1m",
            "processed_path": str(FORWARD_15M_PROCESSED.relative_to(ROOT)),
            "first_timestamp": str(forward_15m.index.min()) if not forward_15m.empty else None,
            "last_timestamp": str(forward_15m.index.max()) if not forward_15m.empty else None,
            "row_count": len(forward_15m),
            "checksum_sha256": _file_sha256(FORWARD_15M_PROCESSED),
        },
    }
    FORWARD_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    FORWARD_MANIFEST.write_text(json.dumps(manifest, indent=2))
    return manifest
