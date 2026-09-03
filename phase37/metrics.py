"""Metrics and comparisons for Phase 37."""

from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import pandas as pd

from phase31.dedupe import dedupe_signals, rth_trading_dates
from phase31.metrics import apply_costs, net_performance, performance, performance
from phase33.displacements import scan_displacements
from phase33.entries import simulate_all_reversal
from phase33.failure import build_failure_events, failure_signals
from phase34.parity import frozen_p33_config
from phase34.config import P33_FAILURE_DEF
from phase36.outcomes import score_outcomes


def load_phase33_batch_fills(market: pd.DataFrame) -> pd.DataFrame:
    """Original Phase 33 batch pipeline — filled RECLAIM_RETEST entries only."""
    displacements = scan_displacements(market)
    # A_MID_4 uses midpoint reclaim only — no opposite-BOS precompute needed
    empty_bos = pd.DataFrame(columns=["bos_bar_index", "bos_timestamp", "bos_direction", "bos_level", "is_choch"])
    failures = build_failure_events(displacements, market, empty_bos)
    signals = dedupe_signals(failure_signals(failures, P33_FAILURE_DEF), market)
    sim = simulate_all_reversal(signals, market, frozen_p33_config())
    filled = sim.loc[sim.filled].copy()
    if filled.empty:
        return filled
    filled["marker_bar_timestamp"] = pd.to_datetime(filled["entry_timestamp"], utc=True)
    filled["signal_type"] = np.where(
        filled["direction"].astype(str).str.lower() == "long", "RL", "RS"
    )
    risk = (filled["entry_price"].astype(float) - filled["stop_price"].astype(float)).abs()
    direction = filled["direction"].astype(str).str.lower()
    filled["target"] = np.where(
        direction == "long",
        filled["entry_price"].astype(float) + 2.5 * risk,
        filled["entry_price"].astype(float) - 2.5 * risk,
    )
    filled["stop"] = filled["stop_price"]
    filled["implementation"] = "ORIGINAL_PHASE33_BATCH"
    filled["net_R"] = apply_costs(filled)
    return filled


def compare_implementations(
    batch: pd.DataFrame,
    single: pd.DataFrame,
    concurrent: pd.DataFrame,
    *,
    ts_col: str = "marker_bar_timestamp",
    price_tol: float = 0.05,
) -> pd.DataFrame:
    def _norm(df, impl):
        if df.empty:
            return pd.DataFrame(columns=[ts_col, "signal_type", "entry_price", "implementation"])
        out = df.copy()
        out[ts_col] = pd.to_datetime(out[ts_col], utc=True).dt.floor("15min")
        out["implementation"] = impl
        return out[[ts_col, "signal_type", "direction", "entry_price", "stop", "target", "implementation", "event_id"] if "event_id" in out.columns else [ts_col, "signal_type", "direction", "entry_price", "stop", "target", "implementation"]]

    b = _norm(batch, "ORIGINAL_PHASE33_BATCH")
    s = _norm(single, "PHASE36_SINGLE_TRACKER")
    c = _norm(concurrent, "PHASE37_CONCURRENT")

    rows = []
    all_keys = set()
    for df in (b, s, c):
        if not df.empty:
            all_keys |= set(zip(df[ts_col], df["signal_type"]))

    for key in sorted(all_keys, key=lambda x: (x[0], x[1])):
        ts, st = key
        rb = b.loc[(b[ts_col] == ts) & (b["signal_type"] == st)] if not b.empty else pd.DataFrame()
        rs = s.loc[(s[ts_col] == ts) & (s["signal_type"] == st)] if not s.empty else pd.DataFrame()
        rc = c.loc[(c[ts_col] == ts) & (c["signal_type"] == st)] if not c.empty else pd.DataFrame()
        row = {"timestamp_ct": ts, "signal_type": st}
        for name, sub in (("batch", rb), ("single", rs), ("concurrent", rc)):
            row[f"{name}_present"] = not sub.empty
            if not sub.empty:
                r = sub.iloc[0]
                row[f"{name}_entry"] = float(r["entry_price"])
                row[f"{name}_stop"] = float(r.get("stop", np.nan))
        if not rc.empty and not rb.empty:
            status = "MATCH"
            if abs(float(rc.iloc[0]["entry_price"]) - float(rb.iloc[0]["entry_price"])) > price_tol:
                status = "WRONG_ENTRY_PRICE"
            row["concurrent_vs_batch"] = status
        elif not rc.empty:
            row["concurrent_vs_batch"] = "EXTRA"
        elif not rb.empty:
            row["concurrent_vs_batch"] = "MISSING"
        else:
            row["concurrent_vs_batch"] = "N/A"
        rows.append(row)
    return pd.DataFrame(rows)


def parity_vs_batch(batch: pd.DataFrame, concurrent: pd.DataFrame) -> pd.DataFrame:
    comp = compare_implementations(batch, pd.DataFrame(), concurrent)
    comp = comp.rename(columns={"concurrent_vs_batch": "parity_status"})
    return comp


def impl_performance(signals: pd.DataFrame, market: pd.DataFrame, *, impl_name: str) -> Dict:
    if signals.empty:
        return {"implementation": impl_name, "N": 0, "AvgR": 0.0, "PF": 0.0, "MaxDD": 0.0, "WinRate": 0.0, "TotalR": 0.0}
    rev = signals.loc[signals["signal_type"].isin(["RL", "RS"])].copy()
    if rev.empty:
        rev = signals.copy()
    outcomes = score_outcomes(rev, market)
    if outcomes.empty:
        return {"implementation": impl_name, "N": 0, "AvgR": 0.0, "PF": 0.0, "MaxDD": 0.0, "WinRate": 0.0, "TotalR": 0.0}
    merged = rev.merge(outcomes, on=["signal_id", "marker_bar_timestamp", "signal_type"], how="left")
    merged["net_R"] = apply_costs(
        merged.assign(entry_price=merged["entry_price"], stop_price=merged["stop"])
    )
    perf = net_performance(merged)
    days = len(rth_trading_dates(market))
    perf["implementation"] = impl_name
    perf["signals_day"] = len(merged) / max(days, 1)
    perf["RL"] = int((merged["signal_type"] == "RL").sum())
    perf["RS"] = int((merged["signal_type"] == "RS").sum())
    return perf


def yearly_perf(signals: pd.DataFrame, market: pd.DataFrame, outcomes: pd.DataFrame | None = None) -> pd.DataFrame:
    if signals.empty:
        return pd.DataFrame()
    rev = signals.loc[signals["signal_type"].isin(["RL", "RS"])].copy()
    oc = outcomes if outcomes is not None else score_outcomes(rev, market)
    merged = rev.merge(oc, on=["signal_id", "marker_bar_timestamp", "signal_type"], how="left")
    merged["result_R"] = merged["realized_R"]
    merged["net_R"] = apply_costs(merged.assign(entry_price=merged["entry_price"], stop_price=merged["stop"]))
    merged["year"] = pd.to_datetime(merged["marker_bar_timestamp"], utc=True).dt.year
    rows = []
    for year, grp in merged.groupby("year"):
        p = performance(grp, col="net_R")
        rows.append({"year": int(year), **p})
    return pd.DataFrame(rows)


def cost_stress(signals: pd.DataFrame, market: pd.DataFrame, outcomes: pd.DataFrame | None = None) -> pd.DataFrame:
    rev = signals.loc[signals["signal_type"].isin(["RL", "RS"])].copy()
    if rev.empty:
        return pd.DataFrame()
    oc = outcomes if outcomes is not None else score_outcomes(rev, market)
    merged = rev.merge(oc, on=["signal_id", "marker_bar_timestamp", "signal_type"], how="left")
    merged["result_R"] = merged["realized_R"]
    rows = []
    for mult in (1.0, 1.5, 2.0):
        df = merged.copy()
        df["net_R"] = apply_costs(df.assign(entry_price=df["entry_price"], stop_price=df["stop"]), multiplier=mult)
        rows.append({"cost_multiplier": mult, **performance(df, col="net_R")})
    return pd.DataFrame(rows)


def restored_analysis(
    single: pd.DataFrame,
    concurrent: pd.DataFrame,
    market: pd.DataFrame,
    *,
    concurrent_outcomes: pd.DataFrame | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """COMMON vs RESTORED reversal signals."""
    def keys(df):
        if df.empty:
            return set()
        t = pd.to_datetime(df["marker_bar_timestamp"], utc=True).dt.floor("15min")
        return set(zip(t, df["signal_type"]))

    s_rev = single.loc[single["signal_type"].isin(["RL", "RS"])] if not single.empty else pd.DataFrame()
    c_rev = concurrent.loc[concurrent["signal_type"].isin(["RL", "RS"])] if not concurrent.empty else pd.DataFrame()
    sk, ck = keys(s_rev), keys(c_rev)
    common = sk & ck
    restored = ck - sk
    only_single = sk - ck

    rows = []
    for label, keyset in (("COMMON", common), ("RESTORED", restored), ("SINGLE_ONLY", only_single)):
        if not keyset:
            continue
        sub = c_rev.copy()
        sub["_key"] = list(zip(pd.to_datetime(sub["marker_bar_timestamp"], utc=True).dt.floor("15min"), sub["signal_type"]))
        sub = sub.loc[sub["_key"].isin(keyset)]
        if label in ("COMMON", "RESTORED") and concurrent_outcomes is not None and not sub.empty:
            sub = sub.merge(concurrent_outcomes, on=["signal_id", "marker_bar_timestamp", "signal_type"], how="left")
            sub["result_R"] = sub["realized_R"]
            sub["net_R"] = apply_costs(sub.assign(entry_price=sub["entry_price"], stop_price=sub["stop"]))
        elif not sub.empty:
            outcomes = score_outcomes(sub, market)
            if not outcomes.empty:
                sub = sub.merge(outcomes, on=["signal_id", "marker_bar_timestamp", "signal_type"], how="left")
                sub["result_R"] = sub["realized_R"]
                sub["net_R"] = apply_costs(sub.assign(entry_price=sub["entry_price"], stop_price=sub["stop"]))
        perf = performance(sub, col="net_R") if "net_R" in sub.columns else net_performance(sub)
        rows.append({"segment": label, "N": len(sub), **perf})
    seg = pd.DataFrame(rows)

    # yearly for RESTORED
    yr_rows = []
    if restored:
        sub = c_rev.copy()
        sub["_key"] = list(zip(pd.to_datetime(sub["marker_bar_timestamp"], utc=True).dt.floor("15min"), sub["signal_type"]))
        sub = sub.loc[sub["_key"].isin(restored)]
        if concurrent_outcomes is not None and not sub.empty:
            sub = sub.merge(concurrent_outcomes, on=["signal_id", "marker_bar_timestamp", "signal_type"], how="left")
            sub["result_R"] = sub["realized_R"]
            sub["net_R"] = apply_costs(sub.assign(entry_price=sub["entry_price"], stop_price=sub["stop"]))
        elif not sub.empty:
            outcomes = score_outcomes(sub, market)
            if not outcomes.empty:
                sub = sub.merge(outcomes, on=["signal_id", "marker_bar_timestamp", "signal_type"], how="left")
                sub["result_R"] = sub["realized_R"]
                sub["net_R"] = apply_costs(sub.assign(entry_price=sub["entry_price"], stop_price=sub["stop"]))
        if not sub.empty and "net_R" in sub.columns:
            sub["year"] = pd.to_datetime(sub["marker_bar_timestamp"], utc=True).dt.year
            for year, grp in sub.groupby("year"):
                yr_rows.append({"segment": "RESTORED", "year": int(year), **performance(grp, col="net_R")})
    yr = pd.DataFrame(yr_rows)
    return seg, yr


def same_bar_conflicts(signals: pd.DataFrame) -> pd.DataFrame:
    rev = signals.loc[signals["signal_type"].isin(["RL", "RS"])].copy()
    if rev.empty:
        return pd.DataFrame()
    rev["ts"] = pd.to_datetime(rev["marker_bar_timestamp"], utc=True).dt.floor("15min")
    grp = rev.groupby(["ts", "signal_type"]).size().reset_index(name="count")
    return grp.loc[grp["count"] > 1]


def concurrency_stats(samples: list) -> pd.DataFrame:
    if not samples:
        return pd.DataFrame()
    arr = np.array(samples)
    return pd.DataFrame(
        [
            {
                "max_concurrent": int(arr.max()),
                "median_concurrent": float(np.median(arr)),
                "p99_concurrent": float(np.percentile(arr, 99)),
                "mean_concurrent": float(arr.mean()),
            }
        ]
    )
