"""Phase56 forward analytics — summaries, checkpoints, bootstrap CI."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from phase45.execution.data_1m import cost_r
from phase53.research.metrics import summarize_r
from phase56.config import CHECKPOINTS, HISTORICAL_OOS, LOGS, PRIMARY_CHECKPOINT, REPORTS, RESULTS, STRONG_CHECKPOINT


def _read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def bootstrap_ci(rs: pd.Series, n_boot: int = 2000, alpha: float = 0.05, seed: int = 42) -> tuple[float, float]:
    if len(rs) < 2:
        return (np.nan, np.nan)
    rng = np.random.default_rng(seed)
    arr = rs.astype(float).values
    means = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_boot)]
    return float(np.quantile(means, alpha / 2)), float(np.quantile(means, 1 - alpha / 2))


def trades_df() -> pd.DataFrame:
    df = _read(LOGS / "s54_forward_trades.csv")
    if df.empty:
        return df
    for c in ("entry_timestamp", "exit_timestamp"):
        if c in df.columns:
            df[c] = df[c].map(pd.Timestamp)
    df["net_R"] = df["net_R"].astype(float)
    return df


def signals_df() -> pd.DataFrame:
    df = _read(LOGS / "s54_forward_signals.csv")
    if not df.empty and "timestamp_ct" in df.columns:
        df["timestamp_ct"] = df["timestamp_ct"].map(pd.Timestamp)
    return df


def events_df() -> pd.DataFrame:
    df = _read(LOGS / "s54_forward_events.csv")
    if not df.empty and "timestamp_ct" in df.columns:
        df["timestamp_ct"] = df["timestamp_ct"].map(pd.Timestamp)
    return df


def checkpoint_metrics(n_trades: int | None = None) -> dict:
    tr = trades_df()
    if tr.empty:
        return {"N": 0}
    if n_trades is not None:
        tr = tr.head(n_trades)
    rs = tr["net_R"]
    sm = summarize_r(tr.assign(timestamp_ct=tr["entry_timestamp"]))
    lo, hi = bootstrap_ci(rs) if len(rs) >= 50 else (np.nan, np.nan)
    long = tr.loc[tr["direction"] == "LONG"]
    short = tr.loc[tr["direction"] == "SHORT"]
    unauth = tr.loc[tr["core_authorized"].astype(int) == 0] if "core_authorized" in tr.columns else pd.DataFrame()
    tr2 = tr.copy()
    if "gross_R" in tr2.columns:
        tr2["net_R_2x"] = tr2["gross_R"].astype(float) - tr2.apply(
            lambda r: cost_r(float(r["entry_price"]), float(r["entry_price"]) * 0.999, 2.0), axis=1
        )
    sig = signals_df()
    days = max((tr["entry_timestamp"].max() - tr["entry_timestamp"].min()).days, 1)
    avgr = sm.get("AvgR")
    retention = float(avgr / HISTORICAL_OOS["AvgR"]) if avgr is not None and np.isfinite(avgr) else np.nan
    return {
        "N": sm.get("N", 0),
        "days": days,
        "episodes_per_day": len(sig) / days if len(sig) else 0.0,
        "AvgR": avgr,
        "median_R": sm.get("median_R"),
        "PF": sm.get("PF"),
        "TotalR": sm.get("TotalR"),
        "MaxDD": sm.get("MaxDD"),
        "win_rate": sm.get("win_rate"),
        "AvgR_CI_lo": lo,
        "AvgR_CI_hi": hi,
        "LONG_N": len(long),
        "LONG_AvgR": float(long["net_R"].mean()) if len(long) else np.nan,
        "SHORT_N": len(short),
        "SHORT_AvgR": float(short["net_R"].mean()) if len(short) else np.nan,
        "CORE_unauth_N": len(unauth),
        "CORE_unauth_AvgR": float(unauth["net_R"].mean()) if len(unauth) else np.nan,
        "CORE_overlap_pct": float(tr["core_authorized"].astype(int).mean()) * 100 if "core_authorized" in tr.columns else 0.0,
        "expectancy_retention_pct": retention * 100 if np.isfinite(retention) else np.nan,
        "cost2x_AvgR": float(tr2["net_R_2x"].mean()) if "net_R_2x" in tr2.columns and len(tr2) else np.nan,
    }


def write_checkpoint_reports() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows = []
    for cp in CHECKPOINTS:
        m = checkpoint_metrics(cp)
        rows.append({"checkpoint": cp, **m})
        (REPORTS / f"checkpoint_{cp}.md").write_text("# Phase56 Checkpoint %d\n\n%s\n" % (cp, "\n".join(f"{k}: {v}" for k, v in m.items())))
    pd.DataFrame(rows).to_csv(RESULTS / "checkpoint_metrics.csv", index=False)


def daily_summary() -> pd.DataFrame:
    ev = events_df()
    sig = signals_df()
    tr = trades_df()
    if ev.empty:
        return pd.DataFrame()
    ev["date"] = ev["timestamp_ct"].map(lambda t: pd.Timestamp(t).date())
    sig["date"] = sig["timestamp_ct"].map(lambda t: pd.Timestamp(t).date()) if not sig.empty else pd.Series(dtype=object)
    tr["date"] = tr["entry_timestamp"].map(lambda t: pd.Timestamp(t).date()) if not tr.empty else pd.Series(dtype=object)
    rows = []
    cum = peak = max_dd = 0.0
    for d in sorted(ev["date"].unique()):
        de = ev.loc[ev["date"] == d]
        ds = sig.loc[sig["date"] == d] if not sig.empty else pd.DataFrame()
        dt = tr.loc[tr["date"] == d] if not tr.empty else pd.DataFrame()
        day_r = float(dt["net_R"].sum()) if len(dt) else 0.0
        cum += day_r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
        rows.append({
            "date": str(d),
            "events": len(de),
            "D10_events": int(de["D10_pass"].astype(str).str.lower().eq("true").sum()),
            "episodes": len(ds),
            "long_signals": int((ds["direction"] == "LONG").sum()) if len(ds) else 0,
            "short_signals": int((ds["direction"] == "SHORT").sum()) if len(ds) else 0,
            "suppressed_events": int(de["episode_status"].eq("SUPPRESSED").sum()) if "episode_status" in de.columns else 0,
            "closed_trades": len(dt),
            "wins": int((dt["net_R"] > 0).sum()) if len(dt) else 0,
            "losses": int((dt["net_R"] <= 0).sum()) if len(dt) else 0,
            "net_R": day_r,
            "cumulative_R": cum,
            "current_DD": peak - cum,
            "max_DD": max_dd,
        })
    out = pd.DataFrame(rows)
    out.to_csv(LOGS / "s54_daily_summary.csv", index=False)
    return out


def weekly_summary() -> pd.DataFrame:
    tr = trades_df()
    if tr.empty:
        return pd.DataFrame()
    tr["week"] = tr["entry_timestamp"].map(lambda t: pd.Timestamp(t).to_period("W"))
    rows = [summarize_r(g.assign(timestamp_ct=g["entry_timestamp"])) | {"week": str(w)} for w, g in tr.groupby("week")]
    out = pd.DataFrame(rows)
    out.to_csv(LOGS / "s54_weekly_summary.csv", index=False)
    return out


def direction_results() -> pd.DataFrame:
    tr = trades_df()
    if tr.empty:
        return pd.DataFrame()
    rows = [{"direction": d, **summarize_r(g.assign(timestamp_ct=g["entry_timestamp"]))} for d, g in tr.groupby("direction")]
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "direction_results.csv", index=False)
    return out


def core_overlap_results() -> pd.DataFrame:
    tr = trades_df()
    if tr.empty:
        return pd.DataFrame()
    auth = tr.loc[tr["core_authorized"].astype(int) == 1]
    unauth = tr.loc[tr["core_authorized"].astype(int) == 0]
    rows = [
        {"segment": "CORE_AUTHORIZED", **summarize_r(auth.assign(timestamp_ct=auth["entry_timestamp"]))},
        {"segment": "CORE_UNAUTHORIZED", **summarize_r(unauth.assign(timestamp_ct=unauth["entry_timestamp"]))},
        {"segment": "ALL", **summarize_r(tr.assign(timestamp_ct=tr["entry_timestamp"]))},
    ]
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS / "core_overlap_results.csv", index=False)
    return out


def signal_frequency() -> pd.DataFrame:
    ev = events_df()
    sig = signals_df()
    if ev.empty:
        return pd.DataFrame()
    d10 = ev.loc[ev["D10_pass"].astype(str).str.lower().eq("true")]
    days = max((pd.Timestamp(ev["timestamp_ct"].max()) - pd.Timestamp(ev["timestamp_ct"].min())).days, 1)
    row = {
        "forward_days": days,
        "raw_events": len(ev),
        "d10_events": len(d10),
        "episodes": len(sig),
        "d10_per_day": len(d10) / days,
        "episodes_per_day": len(sig) / days,
        "reduction_pct": (1 - len(sig) / max(len(d10), 1)) * 100,
        "historical_d10_per_day": HISTORICAL_OOS["d10_events_day"],
        "historical_episodes_per_day": HISTORICAL_OOS["episodes_day"],
    }
    out = pd.DataFrame([row])
    out.to_csv(RESULTS / "signal_frequency.csv", index=False)
    return out


def evaluate_verdict() -> dict:
    m = checkpoint_metrics()
    n = int(m.get("N", 0))
    avgr = m.get("AvgR")
    pf_v = m.get("PF")
    unauth = m.get("CORE_unauth_AvgR")
    c2x = m.get("cost2x_AvgR")
    if n < PRIMARY_CHECKPOINT:
        verdict = "INCONCLUSIVE"
    else:
        criteria = [
            avgr is not None and avgr > 0,
            pf_v is not None and pf_v > 1,
            unauth is not None and unauth > 0,
            c2x is not None and c2x > 0,
        ]
        if all(criteria) and n >= STRONG_CHECKPOINT:
            verdict = "PASS"
        elif sum(criteria) >= 2:
            verdict = "INCONCLUSIVE"
        else:
            verdict = "FAIL"
    return {"verdict": verdict, **m}
