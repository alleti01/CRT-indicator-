#!/usr/bin/env python3
"""Build manual TV review sample restricted to July–August 2026."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase60.python.arrays import build_market_arrays_phase60
from phase69.python.entry_freeze import executions, load_frozen_entries
from phase71.python.canonical_trader import TraderConfig, run_one_position

MANUAL72 = ROOT / "phase72" / "manual_review"
MANUAL72A = ROOT / "phase72a" / "manual_review"
START = pd.Timestamp("2026-07-01", tz="America/Chicago")
END = pd.Timestamp("2026-09-01", tz="America/Chicago")
RNG = np.random.default_rng(202607)


def _sample_pool(df: pd.DataFrame, k: int, seed: int) -> pd.DataFrame:
    if len(df) == 0 or k <= 0:
        return df.iloc[0:0]
    return df.sample(min(k, len(df)), random_state=seed)


def build_sample(n: int = 100) -> pd.DataFrame:
    entries = load_frozen_entries()
    execs = executions(entries)
    m = build_market_arrays_phase60()
    trades, _, _ = run_one_position(execs, m, TraderConfig(enable_t5=True))

    trades = trades.merge(
        entries[["trade_id", "entry_ts", "signal_i"]],
        on="trade_id",
        how="left",
    )
    trades["entry_time"] = pd.to_datetime(trades["entry_ts"])
    if trades["entry_time"].dt.tz is None:
        trades["entry_time"] = trades["entry_time"].dt.tz_localize("America/Chicago")

    window = trades[(trades["entry_time"] >= START) & (trades["entry_time"] < END)].copy()
    if len(window) == 0:
        raise SystemExit("No trades in July–August 2026 window")

    pools = {
        "target": window[window["exit_reason"] == "M0_TARGET"],
        "stop": window[window["exit_reason"] == "M0_STOP"],
        "t5": window[window["exit_reason"] == "T5_NO_PROGRESS"],
        "maxhold": window[window["exit_reason"] == "MAX_HOLD_60M"],
    }
    targets = {"target": 20, "stop": 15, "t5": 20, "maxhold": 10}
    parts = []
    for label, k in targets.items():
        parts.append(_sample_pool(pools[label], k, int(RNG.integers(1e9))))

    sample = pd.concat(parts).drop_duplicates("trade_id")
    remaining = window[~window["trade_id"].isin(sample["trade_id"])]
    need = max(0, n - len(sample))
    if need:
        sample = pd.concat([sample, _sample_pool(remaining, need, 42)]).drop_duplicates("trade_id")

    sample = sample.sort_values("entry_time").head(n).reset_index(drop=True)
    sample["signal_time"] = sample["entry_time"] - pd.Timedelta(minutes=1)
    sample["entry_time_ny"] = sample["entry_time"].dt.tz_convert("America/New_York")
    sample["signal_time_ny"] = sample["signal_time"].dt.tz_convert("America/New_York")
    sample["review_window"] = "2026-07-01 to 2026-08-31 (TV: America/New_York on x-axis)"
    return sample


def write_templates(sample: pd.DataFrame) -> None:
    MANUAL72.mkdir(parents=True, exist_ok=True)
    MANUAL72A.mkdir(parents=True, exist_ok=True)

    sample.to_csv(MANUAL72 / "sample.csv", index=False)
    sample.to_csv(MANUAL72 / "sample_jul_aug_2026.csv", index=False)
    sample.to_csv(MANUAL72A / "sample_jul_aug_2026.csv", index=False)

    log = sample.copy()
    for col in [
        "TV_signal_time", "TV_entry", "TV_direction", "TV_ATR", "TV_stop", "TV_target",
        "TV_T5", "TV_exit", "TV_reason", "PASS_FAIL", "notes",
    ]:
        log[col] = ""
    log.to_csv(MANUAL72 / "manual_review_log_template.csv", index=False)

    e2e_cols = [
        "trade_id", "instrument", "python_signal_time", "tv_signal_time", "signal_match",
        "python_direction", "tv_direction", "direction_match",
        "python_entry_time", "tv_entry_time", "entry_time_match",
        "python_entry", "tv_entry", "entry_price_match",
        "python_atr", "tv_atr", "atr_match",
        "python_stop", "tv_stop", "stop_match",
        "python_target", "tv_target", "target_match",
        "python_t5_time", "tv_t5_time", "t5_time_match",
        "python_mfe_t5", "tv_mfe_t5", "mfe_match",
        "python_exit_time", "tv_exit_time", "exit_time_match",
        "python_reason", "tv_reason", "ohlc_match", "classification", "notes",
    ]
    e2e = pd.DataFrame({
        "trade_id": sample["trade_id"],
        "instrument": "NQ1! (TV) vs LW continuous (Python)",
        "python_direction": sample["direction"],
        "python_signal_time_ny": sample["signal_time_ny"].dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "python_entry_time_ny": sample["entry_time_ny"].dt.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "python_signal_time": sample["signal_time"].astype(str),
        "python_entry_time": sample["entry_time"].astype(str),
        "python_entry": sample["entry_price"],
        "python_atr": sample["initial_atr"],
        "python_stop": sample["stop_price"],
        "python_target": sample["target_price"],
        "python_t5_time": sample.get("t5_time", ""),
        "python_mfe_t5": sample.get("mfe_at_t5_r", ""),
        "python_exit_time": sample.get("exit_time", ""),
        "python_reason": sample["exit_reason"],
        "review_window": sample["review_window"],
    })
    for c in e2e_cols:
        if c not in e2e.columns:
            e2e[c] = ""
    e2e = e2e[e2e_cols + ["review_window"]]
    e2e.to_csv(MANUAL72A / "end_to_end_review.csv", index=False)

    meta = {
        "window_start": str(START),
        "window_end": str(END),
        "n_sample": len(sample),
        "n_available_in_window": int(
            len(sample)  # placeholder overwritten below
        ),
        "exit_reason_counts": sample["exit_reason"].value_counts().to_dict(),
        "random_seed": 202607,
    }
    # recount available
    entries = load_frozen_entries()
    execs = executions(entries)
    m = build_market_arrays_phase60()
    trades, _, _ = run_one_position(execs, m, TraderConfig(enable_t5=True))
    trades["entry_time"] = pd.to_datetime(trades["entry_time"])
    if trades["entry_time"].dt.tz is None:
        trades["entry_time"] = trades["entry_time"].dt.tz_localize("America/Chicago")
    meta["n_available_in_window"] = int(
        ((trades["entry_time"] >= START) & (trades["entry_time"] < END)).sum()
    )
    (MANUAL72A / "sample_jul_aug_2026_meta.json").write_text(json.dumps(meta, indent=2, default=str))


def main():
    sample = build_sample(100)
    write_templates(sample)
    print(f"Wrote {len(sample)} trades (Jul–Aug 2026)")
    print(sample["exit_reason"].value_counts().to_string())
    print(f"Range: {sample['entry_time'].min()} → {sample['entry_time'].max()}")


if __name__ == "__main__":
    main()
