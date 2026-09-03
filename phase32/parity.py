"""Python parity reference for Phase 32 Momentum Displacement Pine."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from phase16.resample import cme_session_date
from phase29.simulator import SimConfig
from phase31.config import hold_bars
from phase31.data import load_market_15m
from phase31.dedupe import rth_trading_dates
from phase31.metrics import apply_costs, daily_distribution, net_performance, simulate_all
from phase31.dedupe import dedupe_signals, filter_rth_signals
from phase31.signals import _scan_momentum_displacement

from .config import (
    COMMON_END,
    COMMON_START,
    ERAS,
    ENTRY_MODEL,
    MAX_HOLD_BARS,
    PHASE31_DRY_STRETCH_REPORTED,
    STOP_ATR,
    TARGET_R,
)


def frozen_sim_config() -> SimConfig:
    return SimConfig(
        entry_model=ENTRY_MODEL,
        stop_atr=STOP_ATR,
        target_r=TARGET_R,
        max_bars=MAX_HOLD_BARS,
        management="FIXED",
    )


def _load_wf_momentum_trades(market: pd.DataFrame) -> pd.DataFrame:
    from phase32.config import ROOT

    path = ROOT / "phase31" / "results" / "daily_frequency_entry" / "walk_forward_trades.csv"
    if not path.exists():
        return pd.DataFrame()
    wf = pd.read_csv(path)
    wf = wf.loc[wf["architecture"] == "MOMENTUM_DISPLACEMENT"].copy()
    wf["entry_timestamp"] = pd.to_datetime(wf["entry_timestamp"], utc=True).dt.tz_convert(market.index.tz)
    return wf


def extract_frozen_signals(market: pd.DataFrame) -> pd.DataFrame:
    raw = _scan_momentum_displacement(market)
    raw = filter_rth_signals(raw)
    return dedupe_signals(raw, market, max_hold_bars=6)


def audit_dry_stretch(
    trades: pd.DataFrame,
    market: pd.DataFrame,
    *,
    eligible_start: str | None = None,
    eligible_end: str | None = None,
) -> Dict[str, Any]:
    """Audit longest consecutive RTH days with zero actionable fills."""
    rth_days = rth_trading_dates(market)
    if eligible_start:
        start = pd.Timestamp(eligible_start).normalize()
        rth_days = rth_days[rth_days >= start]
    if eligible_end:
        end = pd.Timestamp(eligible_end).normalize()
        rth_days = rth_days[rth_days <= end]

    if trades.empty:
        longest = len(rth_days)
        return {
            "longest_dry_stretch": int(longest),
            "eligible_rth_days": int(len(rth_days)),
            "zero_signal_days": int(len(rth_days)),
        }

    ts = pd.to_datetime(trades["entry_timestamp"], utc=True).dt.tz_convert(market.index.tz)
    day_counts = (
        pd.Series([cme_session_date(pd.DatetimeIndex([t]))[0] for t in ts])
        .value_counts()
        .reindex(rth_days, fill_value=0)
    )
    stretches: List[int] = []
    cur = 0
    for c in day_counts.to_numpy():
        if c == 0:
            cur += 1
            stretches.append(cur)
        else:
            cur = 0
    return {
        "longest_dry_stretch": int(max(stretches) if stretches else 0),
        "eligible_rth_days": int(len(rth_days)),
        "zero_signal_days": int((day_counts == 0).sum()),
        "mean_trades_day": float(day_counts.mean()),
    }


def build_parity_reference(
    *,
    start: str = COMMON_START,
    end: str = COMMON_END,
) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    market = load_market_15m().loc[start:end]
    signals = extract_frozen_signals(market)
    pos_map = {ts: i for i, ts in enumerate(market.index)}
    sim = simulate_all(signals, market, frozen_sim_config())
    filled = sim.loc[sim.filled].copy()
    if filled.empty:
        return pd.DataFrame(), pd.DataFrame(), {"N": 0}

    meta = signals[["signal_id", "entry_timestamp", "bos_timestamp", "event_id"]].rename(
        columns={"entry_timestamp": "displacement_time"}
    )
    filled = filled.merge(meta, on="signal_id", how="left")
    filled["trade_id"] = filled["signal_id"].astype(int)
    if "event_id" not in filled.columns and "event_id_y" in filled.columns:
        filled["event_id"] = filled["event_id_y"]

    filled["gross_R"] = filled["result_R"].astype(float)
    filled["net_R"] = apply_costs(filled, multiplier=1.0)
    filled["cost_R"] = filled["gross_R"] - filled["net_R"]
    risk = (filled["entry_price"].astype(float) - filled["stop_price"].astype(float)).abs()
    direction = filled["direction"].astype(str).str.lower()
    filled["target_price"] = np.where(
        direction == "long",
        filled["entry_price"].astype(float) + TARGET_R * risk,
        filled["entry_price"].astype(float) - TARGET_R * risk,
    )
    filled["atr"] = [
        float(market.iloc[pos_map[pd.Timestamp(ts)]]["atr"])
        if pd.Timestamp(ts) in pos_map
        else float("nan")
        for ts in filled["entry_timestamp"]
    ]
    if "bos_timestamp_y" in filled.columns:
        filled["bos_timestamp"] = filled["bos_timestamp_y"]
    elif "bos_timestamp_x" in filled.columns and "bos_timestamp" not in filled.columns:
        filled["bos_timestamp"] = filled["bos_timestamp_x"]

    filled["bos_level"] = filled.apply(
        lambda r: float(market.iloc[pos_map[pd.Timestamp(r["bos_timestamp"])]].high)
        if str(r["direction"]).lower() == "long"
        else float(market.iloc[pos_map[pd.Timestamp(r["bos_timestamp"])]].low),
        axis=1,
    )

    out = filled.rename(
        columns={
            "entry_timestamp": "entry_time",
            "exit_timestamp": "exit_time",
        }
    ).copy()
    if "event_id" not in out.columns:
        out["event_id"] = ""
    out["signal_time"] = out["displacement_time"]
    out["bos_time"] = out["bos_timestamp"]
    out["retest_time"] = out["entry_time"]

    cols = [
        "trade_id",
        "signal_time",
        "displacement_time",
        "direction",
        "bos_time",
        "bos_level",
        "retest_time",
        "entry_time",
        "entry_price",
        "atr",
        "stop_price",
        "target_price",
        "exit_time",
        "exit_price",
        "exit_reason",
        "gross_R",
        "cost_R",
        "net_R",
        "bars_in_trade",
        "mfe_r",
        "mae_r",
        "event_id",
    ]
    reference = out[cols].sort_values("entry_time").reset_index(drop=True)
    windows = build_parity_windows(reference)
    perf = net_performance(filled.assign(net_R=filled["net_R"]))
    daily_full = daily_distribution(filled, market)
    dry_full = audit_dry_stretch(filled, market)
    dry_wf = audit_dry_stretch(filled, market, eligible_start="2020-01-01", eligible_end=COMMON_END)
    dry_bug = audit_dry_stretch(
        _load_wf_momentum_trades(market),
        market,
    )
    meta = {
        "N": int(len(reference)),
        **perf,
        "daily_full_history": daily_full,
        "dry_stretch_audit": {
            "phase31_reported": PHASE31_DRY_STRETCH_REPORTED,
            "full_frozen_fills": dry_full,
            "wf_eligible_period_2020_plus": dry_wf,
            "buggy_wf_trades_vs_full_calendar": dry_bug,
            "cause": (
                "Phase 31 daily_distribution counted stitched WF fills (2020-2026 test folds only) "
                "against the full 2018-2026 RTH calendar. The ~515-day stretch is almost entirely "
                "the 2018-2019 pre-test period with zero WF trades, not a strategy dry spell."
            ),
            "correct_full_frozen_longest_dry": dry_full["longest_dry_stretch"],
            "correct_wf_period_longest_dry": dry_wf["longest_dry_stretch"],
        },
    }
    return reference, windows, meta


def build_parity_windows(reference: pd.DataFrame, per_bucket: int = 3) -> pd.DataFrame:
    rows: List[dict] = []
    if reference.empty:
        return pd.DataFrame()

    buckets = [
        ("WIN_TARGET", reference.loc[reference.exit_reason == "TARGET"]),
        ("LOSS_STOP", reference.loc[reference.exit_reason == "STOP"]),
        ("TIME_EXIT", reference.loc[reference.exit_reason == "TIME"]),
        ("LONG", reference.loc[reference.direction == "Long"]),
        ("SHORT", reference.loc[reference.direction == "Short"]),
    ]
    for label, pool in buckets:
        if pool.empty:
            continue
        for _, row in pool.head(per_bucket).iterrows():
            rows.append(
                {
                    "window_id": label,
                    "trade_id": int(row.trade_id),
                    "direction": row.direction,
                    "displacement_time": row.displacement_time,
                    "bos_time": row.bos_time,
                    "bos_level": row.bos_level,
                    "entry_time": row.entry_time,
                    "entry_price": row.entry_price,
                    "stop_price": row.stop_price,
                    "target_price": row.target_price,
                    "exit_time": row.exit_time,
                    "exit_price": row.exit_price,
                    "exit_reason": row.exit_reason,
                    "net_R": row.net_R,
                }
            )

    for era_name, era_start, era_end in ERAS:
        era = reference.loc[
            (reference["entry_time"] >= pd.Timestamp(era_start, tz=reference["entry_time"].dt.tz))
            & (reference["entry_time"] <= pd.Timestamp(era_end, tz=reference["entry_time"].dt.tz))
        ]
        if era.empty:
            continue
        for _, row in era.head(2).iterrows():
            rows.append(
                {
                    "window_id": f"ERA_{era_name}",
                    "trade_id": int(row.trade_id),
                    "direction": row.direction,
                    "displacement_time": row.displacement_time,
                    "entry_time": row.entry_time,
                    "entry_price": row.entry_price,
                    "stop_price": row.stop_price,
                    "target_price": row.target_price,
                    "exit_reason": row.exit_reason,
                    "net_R": row.net_R,
                }
            )
    return pd.DataFrame(rows)
