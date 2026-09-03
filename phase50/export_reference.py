"""Export Python reference signals for Pine parity comparison."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from phase45.execution.confirm import confirm_b1
from phase45.execution.data_1m import load_market_1m
from phase45.execution.simulate import simulate_1m

from .config import FROZEN_B1_WINDOW_MIN, RESULTS, TIMEZONE


def _setup_code(st: str) -> str:
    return str(st)


def _tier_from_score(score: float, accepted: bool) -> str:
    if not accepted:
        return "C"
    if score >= 63.198239617422814:
        return "A+"
    if score >= 46.076841180646284:
        return "A"
    if score >= 36.49346328963349:
        return "B"
    return "C"


def build_reference_signals(*, window_min: int = FROZEN_B1_WINDOW_MIN) -> pd.DataFrame:
    """Build event-level reference from frozen walk-forward B1@window + M0 simulate."""
    wf = pd.read_csv(
        Path(__file__).resolve().parents[1] / "phase45" / "results" / "15m_context_1m_execution" / "walk_forward_results.csv",
        parse_dates=["marker_bar_timestamp", "actionable_timestamp"],
    )
    prefix = f"B1_w{window_min}"
    fill_col = f"{prefix}_filled"
    if fill_col not in wf.columns:
        raise ValueError(f"missing column {fill_col}")

    filled = wf.loc[wf[fill_col].astype(bool)].copy()
    market = load_market_1m()
    pos = {ts: i for i, ts in enumerate(market.index)}

    rows: list[dict] = []
    for _, sig in filled.iterrows():
        sid = int(sig["signal_id"])
        p44_ts = pd.Timestamp(sig["marker_bar_timestamp"]).tz_convert(TIMEZONE)
        act_ts = pd.Timestamp(sig["actionable_timestamp"]).tz_convert(TIMEZONE)
        direction = str(sig["direction"])
        setup = _setup_code(sig["signal_type"])
        tier = _tier_from_score(float(sig.get("quality_score", np.nan)), True)
        stop = float(sig["stop"])
        target = float(sig["target"])

        entry_time_col = f"{prefix}_entry_time"
        if entry_time_col in sig.index and pd.notna(sig.get(entry_time_col)):
            entry_ts = pd.Timestamp(sig[entry_time_col]).tz_convert(TIMEZONE)
            entry_px = float(sig[f"{prefix}_entry_price"])
            delay = float(sig[f"{prefix}_delay_min"])
            b1_ts = entry_ts
        else:
            fill = confirm_b1(market, pos, act_ts, window_min, direction)
            if not fill.filled:
                continue
            entry_ts = fill.entry_time
            entry_px = fill.entry_price
            delay = fill.delay_min
            b1_ts = entry_ts

        ei = pos.get(entry_ts, int(market.index.searchsorted(entry_ts, side="left")))
        sim = simulate_1m(market, ei, entry_px, stop, target, direction, setup)

        rows.append(
            {
                "signal_id": f"P50-{sid:05d}",
                "phase44_timestamp": p44_ts,
                "direction": direction,
                "phase44_class": tier,
                "setup_type": setup,
                "b1_window": window_min,
                "b1_timestamp": b1_ts,
                "b1_delay": delay,
                "entry_timestamp": entry_ts,
                "entry_price": entry_px,
                "stop": stop,
                "target": target,
                "exit_timestamp": sim["exit_timestamp"],
                "exit_price": np.nan,
                "exit_type": sim["exit_type"],
                "net_r": sim["net_R"],
                "gross_r": sim["gross_R"],
                "actionable_timestamp": act_ts,
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("entry_timestamp").reset_index(drop=True)
    return df


def build_sample_reference(full: pd.DataFrame, *, min_per: int = 10) -> pd.DataFrame:
    """Deterministic chronological sample for first-pass Pine inspection."""
    if full.empty:
        return full.copy()
    parts: list[pd.DataFrame] = []
    for direction in ("Long", "Short"):
        sub = full.loc[full["direction"] == direction]
        parts.append(sub.head(min_per))
    for tier in ("A+", "A", "B"):
        sub = full.loc[full["phase44_class"] == tier]
        parts.append(sub.head(min_per))
    for setup in ("L", "S", "RL", "RS"):
        sub = full.loc[full["setup_type"] == setup]
        parts.append(sub.head(min_per))
    sample = pd.concat(parts).drop_duplicates(subset=["signal_id"]).sort_values("entry_timestamp")
    return sample.reset_index(drop=True)


def write_reference_exports(output: Path = RESULTS) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    full = build_reference_signals()
    sample = build_sample_reference(full)
    full.to_csv(output / "python_reference_signals.csv", index=False)
    sample.to_csv(output / "sample_parity_reference.csv", index=False)
    return {"full_n": len(full), "sample_n": len(sample), "window_min": FROZEN_B1_WINDOW_MIN}
