#!/usr/bin/env python3
"""Phase59I — full historical ORIGINAL vs CAUSAL A vs CAUSAL B comparison."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase58.research.instrument import NQ
from phase58.research.trader_engine import TraderEngine
from phase58b.research.simulation import metrics, simulate_trades
from phase58d.research.baselines import baseline_cde
from phase58f.research.confidence import compute_confidence
from phase58f.research.policies import apply_policy
from phase58g.research.forensics import enrich
from phase58h.research.filters import apply_h_model
from phase58i.research.management import executions_from_trades, simulate_management
from phase58j.research.walkforward_audit import walkforward_splits
from phase59.diagnostics.causal_arrays import build_market_arrays_mode, build_mtf_arrays_mode
from phase59.diagnostics.htf_causality import HTFMode
from phase59.tools.phase59_parity import _load_cfg

TZ = NQ.timezone
OUT = ROOT / "phase59" / "reports"
CACHE = ROOT / "phase59" / "diagnostics" / "cache"
ORIG_P58 = ROOT / "phase59" / "reference" / "p58_trades_cache.parquet"

SETUP_COLS = [
    "market_state",
    "high_subtype",
    "direction_confidence_band",
    "15m_state",
    "5m_state",
]


def _load_p58(mode: HTFMode, cfg: dict) -> pd.DataFrame:
    CACHE.mkdir(parents=True, exist_ok=True)
    if mode == "original":
        if ORIG_P58.exists():
            return pd.read_parquet(ORIG_P58)
        ma = build_market_arrays_mode("original", swing=cfg.get("swing_period", 5))
        eng = TraderEngine(ma, cfg)
        eng.run()
        _, p58 = eng.results()
        p58.to_parquet(ORIG_P58, index=False)
        return p58
    path = CACHE / f"p58_trades_{mode}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    ma = build_market_arrays_mode(mode, swing=cfg.get("swing_period", 5))
    eng = TraderEngine(ma, cfg)
    eng.run()
    _, p58 = eng.results()
    p58.to_parquet(path, index=False)
    return p58


def run_full_canonical(mode: HTFMode, cfg: dict, force: bool = False) -> pd.DataFrame:
    out_path = CACHE / f"canon_full_{mode}.parquet"
    if out_path.exists() and not force:
        print(f"  load cached canon {mode} ({out_path.name})", flush=True)
        df = pd.read_parquet(out_path)
        return _normalize_canon(df)

    print(f"  building full canonical {mode}...", flush=True)
    t0 = time.time()
    p58 = _load_p58(mode, cfg)
    m = build_mtf_arrays_mode(mode, swing_5m=cfg.get("swing_period", 5))
    print(f"  Phase58D variant E ({len(p58):,} p58 trades)...", flush=True)
    _, _, _, exec_e, _, _ = baseline_cde(m, p58, cfg, "E", "P59I")
    d58 = simulate_trades(m, exec_e, cfg, "P59I")
    if not exec_e.empty:
        merge_cols = [
            c
            for c in [
                "setup_id",
                "location_score",
                "direction_score",
                "reaction_score",
                "total_evidence",
                "15m_state",
            ]
            if c in exec_e.columns
        ]
        d58 = d58.merge(exec_e[merge_cols], on="setup_id", how="left")
    d58["signal_m1_i"] = d58.get("signal_m1_i", d58.get("signal_i", d58["entry_i"] - 1))
    d58["trade_id"] = [f"P59I-{mode}-{i+1:06d}" for i in range(len(d58))]

    conf_rows = []
    for i, t in d58.iterrows():
        if i and i % 5000 == 0:
            print(f"    confidence {i}/{len(d58)}", flush=True)
        si = int(t.get("signal_m1_i", t["entry_i"] - 1))
        c = compute_confidence(m, si, t["direction"], cfg)
        c["trade_id"] = t["trade_id"]
        conf_rows.append(c)
    audit = pd.DataFrame(conf_rows)
    full = d58.merge(audit, on="trade_id", how="left", suffixes=("", "_c"))
    full = enrich(full)
    full["p4_status"] = apply_policy(full, "P4")
    full["h1_status"] = apply_h_model(full, "H1")
    full["entry_ts"] = [m.m1_idx[int(i)] for i in full["entry_i"]]
    canon = full.loc[full["h1_status"] == "KEEP"].copy()
    execs = executions_from_trades(canon)
    m1 = simulate_management(m, execs, cfg, "M1_1.0")
    m1["trade_id"] = execs["trade_id"].values[: len(m1)]
    merged = canon.merge(m1, on="trade_id", suffixes=("_d58", "_m1"))
    merged["net_R_m1"] = merged["net_R_m1"].astype(float)
    merged["m1_outcome"] = merged["exit_reason_m1"]
    merged["entry_ts"] = pd.to_datetime(merged["entry_ts"]).dt.tz_convert(TZ)
    merged["htf_mode"] = mode
    merged = _normalize_canon(merged)
    merged.to_parquet(out_path, index=False)
    print(f"  cached {len(merged):,} canon trades in {time.time()-t0:.0f}s", flush=True)
    return merged


def _normalize_canon(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "direction" not in df.columns:
        for c in ("direction_m1", "direction_d58", "original_direction"):
            if c in df.columns:
                df["direction"] = df[c]
                break
    if "net_R_m1" not in df.columns and "net_R" in df.columns:
        df["net_R_m1"] = df["net_R"]
    df["entry_ts"] = pd.to_datetime(df["entry_ts"]).dt.tz_convert(TZ)
    return df


def _metric_row(df: pd.DataFrame, slice_name: str, mode: str) -> dict:
    if df.empty:
        return {"mode": mode, "slice": slice_name, "N": 0}
    rs = df["net_R_m1"].astype(float).values
    m = metrics(rs)
    row = {"mode": mode, "slice": slice_name, **m}
    row["LONG"] = int((df["direction"] == "LONG").sum())
    row["SHORT"] = int((df["direction"] == "SHORT").sum())
    return row


def _chronological(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values("entry_ts").reset_index(drop=True)


def split_walkforward(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    df = _chronological(df)
    splits = walkforward_splits(len(df), cfg["train_end_frac"], cfg["valid_end_frac"])
    rows = []
    mode = df["htf_mode"].iloc[0]
    for name, (a, b) in splits.items():
        rows.append(_metric_row(df.iloc[a:b], f"wf_{name}", mode))
    return pd.DataFrame(rows)


def split_years(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["year"] = df["entry_ts"].dt.year
    rows = []
    mode = df["htf_mode"].iloc[0]
    for yr, g in df.groupby("year"):
        rows.append(_metric_row(g, f"year_{yr}", mode))
    return pd.DataFrame(rows)


def split_direction(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    mode = df["htf_mode"].iloc[0]
    for d in ["LONG", "SHORT"]:
        g = df.loc[df["direction"] == d]
        rows.append(_metric_row(g, f"dir_{d}", mode))
    return pd.DataFrame(rows)


def split_setup_categories(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    mode = df["htf_mode"].iloc[0]
    for col in SETUP_COLS:
        if col not in df.columns:
            continue
        for val, g in df.groupby(col, dropna=False):
            label = str(val) if pd.notna(val) and str(val) else "(empty)"
            rows.append(_metric_row(g, f"{col}={label}", mode))
    return pd.DataFrame(rows)


def rolling_windows(df: pd.DataFrame, months: int = 12, step_months: int = 3) -> pd.DataFrame:
    df = _chronological(df)
    mode = df["htf_mode"].iloc[0]
    if df.empty:
        return pd.DataFrame()
    start = df["entry_ts"].min().normalize()
    end = df["entry_ts"].max()
    rows = []
    cur = start
    while cur + pd.DateOffset(months=months) <= end + pd.Timedelta(days=1):
        w_end = cur + pd.DateOffset(months=months)
        g = df.loc[(df["entry_ts"] >= cur) & (df["entry_ts"] < w_end)]
        if len(g) >= 20:
            rows.append(
                {
                    **_metric_row(g, f"roll_{months}m_{cur.strftime('%Y-%m')}", mode),
                    "window_start": str(cur),
                    "window_end": str(w_end),
                }
            )
        cur = cur + pd.DateOffset(months=step_months)
    return pd.DataFrame(rows)


def stability_summary(year_df: pd.DataFrame, roll_df: pd.DataFrame, mode: str) -> dict:
    y = year_df.loc[year_df["mode"] == mode].copy()
    r = roll_df.loc[roll_df["mode"] == mode].copy()
    out: dict = {"mode": mode}
    if not y.empty:
        out["years_total"] = len(y)
        out["years_positive_avgR"] = int((y["AvgR"] > 0).sum())
        out["years_positive_totalR"] = int((y["TotalR"] > 0).sum())
        tot = y["TotalR"].sum()
        out["top_year_share"] = float(y["TotalR"].max() / tot) if tot > 0 else np.nan
        out["year_avgR_min"] = float(y["AvgR"].min())
        out["year_avgR_median"] = float(y["AvgR"].median())
    if not r.empty:
        out["rolling_windows"] = len(r)
        out["rolling_positive_avgR"] = int((r["AvgR"] > 0).sum())
        out["rolling_positive_totalR"] = int((r["TotalR"] > 0).sum())
        out["rolling_avgR_min"] = float(r["AvgR"].min())
        out["rolling_avgR_median"] = float(r["AvgR"].median())
    return out


def expectancy_verdict(overall: pd.DataFrame) -> dict:
    v = {}
    for mode in ("original", "causal_a", "causal_b"):
        row = overall.loc[overall["mode"] == mode]
        if row.empty:
            v[mode] = {"positive_expectancy": False, "reason": "no trades"}
            continue
        r = row.iloc[0]
        pos = bool(r["AvgR"] > 0 and r["PF"] > 1.0 and r["TotalR"] > 0)
        v[mode] = {
            "positive_expectancy": pos,
            "N": int(r["N"]),
            "AvgR": float(r["AvgR"]),
            "PF": float(r["PF"]),
            "TotalR": float(r["TotalR"]),
            "WinRate": float(r["WinRate"]),
            "MaxDD": float(r["MaxDD"]),
        }
    return v


def run_historical(force: bool = False) -> dict:
    t0 = time.time()
    cfg = _load_cfg()
    modes: list[HTFMode] = ["original", "causal_a", "causal_b"]
    canon: dict[str, pd.DataFrame] = {}
    for mode in modes:
        print(f"=== {mode.upper()} ===", flush=True)
        canon[mode] = run_full_canonical(mode, cfg, force=force)

    overall_rows = []
    wf_rows = []
    year_rows = []
    dir_rows = []
    setup_rows = []
    roll_rows = []
    for mode, df in canon.items():
        overall_rows.append(_metric_row(df, "ALL", mode))
        wf_rows.append(split_walkforward(df, cfg))
        year_rows.append(split_years(df))
        dir_rows.append(split_direction(df))
        setup_rows.append(split_setup_categories(df))
        roll_rows.append(rolling_windows(df, months=12, step_months=3))
        roll_rows.append(rolling_windows(df, months=6, step_months=3))

    overall = pd.DataFrame(overall_rows)
    wf = pd.concat(wf_rows, ignore_index=True)
    years = pd.concat(year_rows, ignore_index=True)
    dirs = pd.concat(dir_rows, ignore_index=True)
    setups = pd.concat(setup_rows, ignore_index=True)
    rolling = pd.concat(roll_rows, ignore_index=True)

    stability = [stability_summary(years, rolling, m) for m in modes]
    expectancy = expectancy_verdict(overall)

    OUT.mkdir(parents=True, exist_ok=True)
    overall.to_csv(OUT / "phase59i_overall.csv", index=False)
    wf.to_csv(OUT / "phase59i_walkforward.csv", index=False)
    years.to_csv(OUT / "phase59i_by_year.csv", index=False)
    dirs.to_csv(OUT / "phase59i_by_direction.csv", index=False)
    setups.to_csv(OUT / "phase59i_by_setup.csv", index=False)
    rolling.to_csv(OUT / "phase59i_rolling.csv", index=False)

    result = {
        "overall": overall.to_dict(orient="records"),
        "walkforward": wf.to_dict(orient="records"),
        "by_year": years.to_dict(orient="records"),
        "by_direction": dirs.to_dict(orient="records"),
        "by_setup": setups.to_dict(orient="records"),
        "rolling": rolling.to_dict(orient="records"),
        "stability": stability,
        "expectancy": expectancy,
        "elapsed_s": round(time.time() - t0, 1),
    }
    (OUT / "phase59i_historical_audit.json").write_text(json.dumps(result, indent=2, default=str))
    write_historical_report(result)
    print(f"Done in {result['elapsed_s']}s", flush=True)
    return result


def write_historical_report(result: dict) -> None:
    exp = result["expectancy"]
    stab = {s["mode"]: s for s in result["stability"]}
    path = OUT / "PHASE59I_HISTORICAL_COMPARISON.md"

    def _lines(records: list, key: str) -> str:
        lines = []
        for r in records:
            if key in r.get("slice", r.get("split", "")) or key in str(r.get("slice", "")):
                pass
        sub = [r for r in records if r.get("slice", "").startswith(key) or r.get("slice") == key]
        if not sub and key.startswith("wf_"):
            sub = [r for r in records if r.get("slice") == key]
        return ""

    o, a, b = exp.get("original", {}), exp.get("causal_a", {}), exp.get("causal_b", {})
    so, sa, sb = stab.get("original", {}), stab.get("causal_a", {}), stab.get("causal_b", {})

    wf = pd.DataFrame(result["walkforward"])
    years = pd.DataFrame(result["by_year"])

    def wf_line(mode: str, split: str) -> str:
        r = wf.loc[(wf["mode"] == mode) & (wf["slice"] == f"wf_{split}")]
        if r.empty:
            return "N=0"
        x = r.iloc[0]
        return f"N={int(x['N'])} AvgR={x['AvgR']:.3f} PF={x['PF']:.2f} TotalR={x['TotalR']:.1f} MaxDD={x['MaxDD']:.1f}"

    year_table = years.pivot_table(index="slice", columns="mode", values="AvgR", aggfunc="first")
    year_tot = years.pivot_table(index="slice", columns="mode", values="TotalR", aggfunc="first")

    body = f"""# PHASE59I — FULL HISTORICAL COMPARISON

Diagnostic only. Frozen parameters. No optimization.

## Overall M1 canonical (H1 KEEP)

| Mode | N | AvgR | PF | TotalR | WinRate | MaxDD |
|------|---|------|-----|--------|---------|-------|
| ORIGINAL | {o.get('N',0)} | {o.get('AvgR',0):.3f} | {o.get('PF',0):.2f} | {o.get('TotalR',0):.1f} | {o.get('WinRate',0):.1%} | {o.get('MaxDD',0):.1f} |
| CAUSAL A | {a.get('N',0)} | {a.get('AvgR',0):.3f} | {a.get('PF',0):.2f} | {a.get('TotalR',0):.1f} | {a.get('WinRate',0):.1%} | {a.get('MaxDD',0):.1f} |
| CAUSAL B | {b.get('N',0)} | {b.get('AvgR',0):.3f} | {b.get('PF',0):.2f} | {b.get('TotalR',0):.1f} | {b.get('WinRate',0):.1%} | {b.get('MaxDD',0):.1f} |

## Positive expectancy survives causally?

| Mode | AvgR>0 & PF>1 & TotalR>0 |
|------|--------------------------|
| ORIGINAL | **{'YES' if o.get('positive_expectancy') else 'NO'}** |
| CAUSAL A (last completed HTF) | **{'YES' if a.get('positive_expectancy') else 'NO'}** |
| CAUSAL B (developing HTF) | **{'YES' if b.get('positive_expectancy') else 'NO'}** |

## Walk-forward (60/20/20 chronological)

| Split | ORIGINAL | CAUSAL A | CAUSAL B |
|-------|----------|----------|----------|
| train | {wf_line('original','train')} | {wf_line('causal_a','train')} | {wf_line('causal_b','train')} |
| validation | {wf_line('original','validation')} | {wf_line('causal_a','validation')} | {wf_line('causal_b','validation')} |
| holdout | {wf_line('original','holdout')} | {wf_line('causal_a','holdout')} | {wf_line('causal_b','holdout')} |

## Stability (not concentrated in isolated periods)

| Metric | ORIGINAL | CAUSAL A | CAUSAL B |
|--------|----------|----------|----------|
| Years with AvgR>0 | {so.get('years_positive_avgR','?')}/{so.get('years_total','?')} | {sa.get('years_positive_avgR','?')}/{sa.get('years_total','?')} | {sb.get('years_positive_avgR','?')}/{sb.get('years_total','?')} |
| Years with TotalR>0 | {so.get('years_positive_totalR','?')} | {sa.get('years_positive_totalR','?')} | {sb.get('years_positive_totalR','?')} |
| Top-year share of TotalR | {so.get('top_year_share',0):.1%} | {sa.get('top_year_share',0):.1%} | {sb.get('top_year_share',0):.1%} |
| 12m rolling windows AvgR>0 | {so.get('rolling_positive_avgR','?')}/{so.get('rolling_windows','?')} | {sa.get('rolling_positive_avgR','?')}/{sa.get('rolling_windows','?')} | {sb.get('rolling_positive_avgR','?')}/{sb.get('rolling_windows','?')} |
| Median year AvgR | {so.get('year_avgR_median',0):.3f} | {sa.get('year_avgR_median',0):.3f} | {sb.get('year_avgR_median',0):.3f} |
| Min year AvgR | {so.get('year_avgR_min',0):.3f} | {sa.get('year_avgR_min',0):.3f} | {sb.get('year_avgR_min',0):.3f} |

## Artifacts

- `phase59i_overall.csv`
- `phase59i_walkforward.csv`
- `phase59i_by_year.csv`
- `phase59i_by_direction.csv`
- `phase59i_by_setup.csv`
- `phase59i_rolling.csv`
- `phase59i_historical_audit.json`

Elapsed: {result['elapsed_s']}s

## Interpretation guide

- **CAUSAL A** = live-safe HTF (last completed bar ≈ TV `lookahead_off`)
- **ORIGINAL** = frozen Python with HTF future leakage
- Positive expectancy under CAUSAL A/B is required for live viability
- High top-year share or few positive rolling windows = unstable / concentrated edge
"""
    path.write_text(body)
    print(f"Wrote {path}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Rebuild cached canon")
    args = ap.parse_args()
    run_historical(force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
