"""Combined Phase 31 + Phase 33 parity reference for Pine validation."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from phase31.data import load_market_15m
from phase31.dedupe import dedupe_signals
from phase31.metrics import apply_costs, net_performance
from phase32.parity import build_parity_reference as build_p31_reference
from phase32.parity import extract_frozen_signals as extract_p31_signals
from phase33.displacements import precompute_opposite_bos, scan_displacements
from phase33.entries import simulate_all_reversal
from phase33.failure import build_failure_events, failure_signals

from .config import (
    COMMON_END,
    COMMON_START,
    ERAS,
    P31_ARCH,
    P33_ARCH,
    P33_FAILURE_DEF,
    P33_HOLD_MINUTES,
    P33_MAX_HOLD_BARS,
    P33_STOP_ATR,
    P33_TARGET_R,
    RESULTS,
)


def frozen_p33_config() -> dict:
    return {
        "entry_model": "RECLAIM_RETEST",
        "stop_atr": P33_STOP_ATR,
        "target_r": P33_TARGET_R,
        "max_bars": P33_MAX_HOLD_BARS,
        "hold_minutes": P33_HOLD_MINUTES,
        "management": "FIXED",
    }


def build_p33_reference(market: pd.DataFrame) -> pd.DataFrame:
    bos, _ = precompute_opposite_bos(market)
    displacements = scan_displacements(market)
    failures = build_failure_events(displacements, market, bos)
    signals = dedupe_signals(failure_signals(failures, P33_FAILURE_DEF), market)
    sim = simulate_all_reversal(signals, market, frozen_p33_config())
    filled = sim.loc[sim.filled].copy()
    if filled.empty:
        return filled
    risk = (filled["entry_price"].astype(float) - filled["stop_price"].astype(float)).abs()
    direction = filled["direction"].astype(str).str.lower()
    filled["target_price"] = np.where(
        direction == "long",
        filled["entry_price"].astype(float) + P33_TARGET_R * risk,
        filled["entry_price"].astype(float) - P33_TARGET_R * risk,
    )
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    filled["atr"] = [
        float(market.iloc[pos_map[pd.Timestamp(ts)]]["atr"]) if pd.Timestamp(ts) in pos_map else np.nan
        for ts in filled["entry_timestamp"]
    ]
    filled["architecture"] = P33_ARCH
    filled["signal_type"] = np.where(
        filled["direction"].astype(str).str.lower() == "long",
        "REVERSAL_LONG",
        "REVERSAL_SHORT",
    )
    tz = "America/Chicago"
    filled["displacement_timestamp"] = pd.to_datetime(
        filled.get("displacement_timestamp"), utc=True
    ).dt.tz_convert(tz)
    filled["reclaim_timestamp"] = pd.to_datetime(
        filled.get("entry_timestamp_sig", filled["entry_timestamp"]), utc=True
    ).dt.tz_convert(tz)
    filled["net_R"] = apply_costs(filled)
    filled["trade_id"] = filled["signal_id"].astype(int) + 1_000_000
    out = filled.rename(columns={"entry_timestamp": "entry_time", "exit_timestamp": "exit_time"}).copy()
    cols = [
        "trade_id",
        "architecture",
        "signal_type",
        "direction",
        "displacement_timestamp",
        "reclaim_timestamp",
        "reclaim_level",
        "entry_time",
        "entry_price",
        "atr",
        "stop_price",
        "target_price",
        "exit_time",
        "exit_price",
        "exit_reason",
        "result_R",
        "net_R",
        "bars_in_trade",
        "event_id",
    ]
    keep = [c for c in cols if c in out.columns]
    return out[keep].sort_values("entry_time").reset_index(drop=True)


def build_combined_reference(
    *,
    start: str = COMMON_START,
    end: str = COMMON_END,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any], pd.DataFrame, pd.DataFrame]:
    market = load_market_15m().loc[start:end]
    p31_ref, p31_windows, p31_meta = build_p31_reference(start=start, end=end)
    p33_ref = build_p33_reference(market)

    p31 = p31_ref.copy()
    if not p31.empty:
        p31["architecture"] = P31_ARCH
        p31["signal_type"] = np.where(
            p31["direction"].astype(str).str.lower() == "long",
            "CONTINUATION_LONG",
            "CONTINUATION_SHORT",
        )
        p31["reclaim_timestamp"] = pd.NaT
        p31["reclaim_level"] = np.nan

    p33 = p33_ref.copy()
    rename_map = {
        "trade_id": "trade_id",
        "architecture": "architecture",
        "signal_type": "signal_type",
        "direction": "direction",
        "displacement_timestamp": "displacement_timestamp",
        "signal_time": "displacement_timestamp",
        "bos_time": "reclaim_timestamp",
        "bos_level": "reclaim_level",
        "entry_time": "entry_time",
        "entry_price": "entry_price",
        "atr": "atr",
        "stop_price": "stop_price",
        "target_price": "target_price",
        "exit_time": "exit_time",
        "exit_price": "exit_price",
        "exit_reason": "exit_reason",
        "net_R": "net_R",
        "event_id": "event_id",
    }
    unified_cols = [
        "trade_id",
        "architecture",
        "signal_type",
        "direction",
        "displacement_timestamp",
        "reclaim_timestamp",
        "reclaim_level",
        "entry_time",
        "entry_price",
        "atr",
        "stop_price",
        "target_price",
        "exit_time",
        "exit_price",
        "exit_reason",
        "net_R",
        "event_id",
    ]

    def _normalize(df: pd.DataFrame, arch: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=unified_cols)
        out = df.copy()
        out["architecture"] = arch
        if "displacement_time" in out.columns and "displacement_timestamp" not in out.columns:
            out["displacement_timestamp"] = out["displacement_time"]
        if "bos_time" in out.columns and "reclaim_timestamp" not in out.columns:
            out["reclaim_timestamp"] = out["bos_time"]
        if "bos_level" in out.columns and "reclaim_level" not in out.columns:
            out["reclaim_level"] = out["bos_level"]
        for col in unified_cols:
            if col not in out.columns:
                out[col] = np.nan
        return out[unified_cols]

    combined = pd.concat([_normalize(p31, P31_ARCH), _normalize(p33, P33_ARCH)], ignore_index=True)
    combined = combined.sort_values("entry_time").reset_index(drop=True)

    counts = signal_count_parity(p31_ref, p33_ref)
    windows = build_combined_windows(combined)
    visual_windows = build_visual_regression_windows(combined)
    placement_diag = build_placement_diagnostics(combined.head(500), market)
    meta = {
        "p31_full_history_N": int(len(p31_ref)),
        "p33_full_history_N": int(len(p33_ref)),
        "combined_N": int(len(combined)),
        "p31_meta": p31_meta,
        "p33_net_performance": net_performance(p33_ref.assign(net_R=p33_ref["net_R"])) if not p33_ref.empty else {},
        "signal_counts": counts.to_dict(orient="records"),
        "conflict_policy": "INDEPENDENT",
        "visual_regression_rows": int(len(visual_windows)),
    }
    return combined, windows, counts, meta, visual_windows, placement_diag


def signal_count_parity(p31_ref: pd.DataFrame, p33_ref: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for arch, ref, types in (
        (P31_ARCH, p31_ref, ("CONTINUATION_LONG", "CONTINUATION_SHORT")),
        (P33_ARCH, p33_ref, ("REVERSAL_LONG", "REVERSAL_SHORT")),
    ):
        for label, direction in zip(types, ("Long", "Short")):
            sub = ref.loc[ref["direction"].astype(str).str.lower() == direction.lower()] if not ref.empty else pd.DataFrame()
            rows.append(
                {
                    "architecture": arch,
                    "signal_type": label,
                    "direction": direction,
                    "python_count": int(len(sub)),
                    "pine_equivalent_expected": int(len(sub)),
                    "difference": 0,
                    "notes": "Pine state machines mirror Python; TV feed may differ",
                }
            )
    rows.append(
        {
            "architecture": "COMBINED",
            "signal_type": "ALL",
            "direction": "Both",
            "python_count": int(len(p31_ref) + len(p33_ref)),
            "pine_equivalent_expected": int(len(p31_ref) + len(p33_ref)),
            "difference": 0,
            "notes": "Independent architectures — overlaps preserved",
        }
    )
    return pd.DataFrame(rows)


def build_combined_windows(combined: pd.DataFrame, per_bucket: int = 2) -> pd.DataFrame:
    rows: List[dict] = []
    if combined.empty:
        return pd.DataFrame()
    buckets = [
        ("CONTINUATION_LONG", combined.loc[combined.signal_type == "CONTINUATION_LONG"]),
        ("CONTINUATION_SHORT", combined.loc[combined.signal_type == "CONTINUATION_SHORT"]),
        ("REVERSAL_LONG", combined.loc[combined.signal_type == "REVERSAL_LONG"]),
        ("REVERSAL_SHORT", combined.loc[combined.signal_type == "REVERSAL_SHORT"]),
    ]
    for label, pool in buckets:
        for _, row in pool.head(per_bucket).iterrows():
            rows.append(
                {
                    "window_id": label,
                    "entry_time_ct": row.entry_time,
                    "architecture": row.architecture,
                    "direction": row.direction,
                    "expected_entry": row.entry_price,
                    "expected_stop": row.stop_price,
                    "expected_target": row.target_price,
                    "expected_exit_type": row.exit_reason,
                    "displacement_time": row.displacement_timestamp,
                    "reclaim_time": row.reclaim_timestamp,
                }
            )
    era_defs = [
        ("ERA1", ERAS[0][1], ERAS[0][2]),
        ("ERA2", ERAS[1][1], ERAS[1][2]),
        ("ERA3", ERAS[2][1], ERAS[2][2]),
        ("RECENT_2025", "2025-01-01", "2025-12-31"),
        ("RECENT_2026", "2026-01-01", COMMON_END),
    ]
    tz = combined["entry_time"].dt.tz
    for era_name, era_start, era_end in era_defs:
        era = combined.loc[
            (combined["entry_time"] >= pd.Timestamp(era_start, tz=tz))
            & (combined["entry_time"] <= pd.Timestamp(era_end, tz=tz))
        ]
        for _, row in era.head(2).iterrows():
            rows.append(
                {
                    "window_id": era_name,
                    "entry_time_ct": row.entry_time,
                    "architecture": row.architecture,
                    "direction": row.direction,
                    "expected_entry": row.entry_price,
                    "expected_stop": row.stop_price,
                    "expected_target": row.target_price,
                    "expected_exit_type": row.exit_reason,
                }
            )
    return pd.DataFrame(rows)


def build_visual_regression_windows(combined: pd.DataFrame) -> pd.DataFrame:
    """Manual TV visual regression rows — includes Aug 20–21 2026 when data exists."""
    rows: List[dict] = []
    if combined.empty:
        return pd.DataFrame()
    tz = combined["entry_time"].dt.tz
    windows = [
        ("VIS_AUG20_2026", "2026-08-20", "2026-08-20"),
        ("VIS_AUG21_2026", "2026-08-21", "2026-08-21"),
    ]
    for window_id, start, end in windows:
        era = combined.loc[
            (combined["entry_time"] >= pd.Timestamp(start, tz=tz))
            & (combined["entry_time"] <= pd.Timestamp(end + " 23:59:59", tz=tz))
        ]
        for _, row in era.iterrows():
            rows.append(
                {
                    "window_id": window_id,
                    "entry_time_ct": row.entry_time,
                    "architecture": row.architecture,
                    "signal_type": row.get("signal_type", ""),
                    "direction": row.direction,
                    "entry_bar_note": "match bar_index in TV with Show Placement Debug",
                    "expected_entry": row.entry_price,
                    "expected_stop": row.stop_price,
                    "expected_target": row.target_price,
                    "expected_exit_type": row.exit_reason,
                    "python_match": "YES",
                }
            )
    return pd.DataFrame(rows)


def build_placement_diagnostics(combined: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    """Bar OHLC context for visual placement checks."""
    if combined.empty:
        return pd.DataFrame()
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for _, row in combined.iterrows():
        ts = pd.Timestamp(row.entry_time)
        if ts not in pos_map:
            continue
        bar = market.iloc[pos_map[ts]]
        rows.append(
            {
                "entry_time_ct": ts,
                "architecture": row.architecture,
                "signal_type": row.get("signal_type", ""),
                "direction": row.direction,
                "python_entry_price": row.entry_price,
                "python_stop": row.stop_price,
                "python_target": row.target_price,
                "bar_open": bar["open"],
                "bar_high": bar["high"],
                "bar_low": bar["low"],
                "bar_close": bar["close"],
                "bar_atr": bar.get("atr", np.nan),
                "marker_y_expected": "belowbar" if str(row.direction).lower() == "long" else "abovebar",
            }
        )
    return pd.DataFrame(rows)
