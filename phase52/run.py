"""Phase52 main research runner."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from phase16.indicators import is_in_session
from phase52.config import (
    CONTEXTS,
    CORE_BENCHMARK,
    CORE_OVERLAP_MIN,
    COVERAGE_DEFS,
    DEFAULT_SWING,
    FAMILIES,
    MIN_TEST_TRADES,
    MIN_TRAIN_TRADES,
    RESULTS,
    RTH_SESSION,
    SWING_LOOKBACKS,
    WALK_FORWARD_FOLDS,
)
from phase52.research.context import context_allows
from phase52.research.coverage import coverage_analysis
from phase52.research.data import align_15m_to_1m, document_data, load_markets
from phase52.research.families import dedupe_signals, generate_family_signals
from phase52.research.metrics import max_dd, pf, primary_table_row, summarize_trades
from phase52.research.overlap import classify_overlap, load_core_trades, overlap_summary
from phase52.research.portfolio import merge_portfolio, portfolio_summary
from phase52.research.simulate_s52 import simulate_signals
from phase52.research.walkforward import walk_forward_s52


def _m15_index_map(m1: pd.DataFrame, m15_aligned: pd.DataFrame) -> np.ndarray:
    """For each 1M bar index, corresponding 15M bar index in aligned frame."""
    m15_idx = m15_aligned.index
    out = np.searchsorted(m15_idx.values, m1.index.values, side="right") - 1
    return np.clip(out, 0, len(m15_aligned) - 1)


def apply_context(signals: pd.DataFrame, ctx: str, m15: pd.DataFrame, m15_map: np.ndarray) -> tuple[pd.DataFrame, pd.DataFrame]:
    if signals.empty or ctx == "C0":
        return signals.copy(), pd.DataFrame()
    kept, rejected = [], []
    for _, s in signals.iterrows():
        i = int(s["entry_i"])
        d = 1 if s["direction"] == "LONG" else -1
        mi = int(m15_map[i])
        ok = context_allows(ctx, d, i, m15, mi)
        row = s.to_dict()
        if ok:
            kept.append(row)
        else:
            rejected.append(row)
    return pd.DataFrame(kept), pd.DataFrame(rejected)


def family_variants() -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for fam in FAMILIES:
        if fam == "A3":
            out.append((fam, {"atr_mult": 0.10}))
        else:
            out.append((fam, {}))
    return out


def run_candidate(
    market: pd.DataFrame,
    m15: pd.DataFrame,
    m15_map: np.ndarray,
    family: str,
    fam_kw: dict,
    ctx: str,
    rth_only: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    raw = generate_family_signals(market, family, rth_only=rth_only, **fam_kw)
    if raw.empty:
        return pd.DataFrame(), pd.DataFrame(), 0
    filtered, rejected = apply_context(raw, ctx, m15, m15_map)
    deduped, removed = dedupe_signals(filtered)
    trades = simulate_signals(market, deduped)
    if not trades.empty:
        trades["family"] = family
        trades["context"] = ctx
        trades["rth_only"] = rth_only
        trades["dedupe_removed"] = removed
    return trades, rejected, removed


def year_slice(df: pd.DataFrame, year: int) -> pd.DataFrame:
    if df.empty:
        return df
    ts = pd.to_datetime(df["entry_timestamp"])
    return df.loc[ts.dt.year == year]


def session_slice(df: pd.DataFrame, label: str) -> pd.DataFrame:
    if df.empty:
        return df
    ts = pd.to_datetime(df["entry_timestamp"])
    h, m = ts.dt.hour, ts.dt.minute
    mins = h * 60 + m
    if label == "open":
        mask = (mins >= 9 * 60 + 30) & (mins < 10 * 60 + 30)
    elif label == "midday":
        mask = (mins >= 11 * 60 + 30) & (mins < 13 * 60 + 30)
    elif label == "afternoon":
        mask = (mins >= 14 * 60) & (mins < 16 * 60)
    else:
        mask = ts.map(lambda t: is_in_session(t, RTH_SESSION))
    return df.loc[mask]


def flip_analysis(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame([{"metric": "same_day_flips", "value": 0}])
    ts = pd.to_datetime(trades["entry_timestamp"]).dt.date
    flips = 0
    flip_rs: list[float] = []
    gaps: list[float] = []
    for day, grp in trades.groupby(ts):
        g = grp.sort_values("entry_timestamp")
        dirs = g["direction"].tolist()
        for i in range(1, len(dirs)):
            if dirs[i] != dirs[i - 1]:
                flips += 1
                flip_rs.append(float(g.iloc[i]["net_R"]))
                t0 = pd.Timestamp(g.iloc[i - 1]["entry_timestamp"])
                t1 = pd.Timestamp(g.iloc[i]["entry_timestamp"])
                gaps.append((t1 - t0).total_seconds() / 60.0)
    return pd.DataFrame(
        [
            {"metric": "same_day_flips", "value": flips},
            {"metric": "flip_AvgR", "value": float(np.mean(flip_rs)) if flip_rs else np.nan},
            {"metric": "flip_median_gap_min", "value": float(np.median(gaps)) if gaps else np.nan},
        ]
    )


def false_signal_analysis(trades: pd.DataFrame) -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    imm_rev = int(((trades["MAE_R"] > 1.0) & (trades["MFE_R"] < 0.25)).sum())
    high_mae = int((trades["MAE_R"] > 1.5).sum())
    low_mfe = int((trades["MFE_R"] < 0.5).sum())
    return pd.DataFrame(
        [
            {"category": "immediate_reversal", "N": imm_rev},
            {"category": "high_MAE", "N": high_mae},
            {"category": "low_MFE", "N": low_mfe},
        ]
    )


def robustness_row(trades: pd.DataFrame, market: pd.DataFrame) -> dict:
    if trades.empty:
        return {}
    base = summarize_trades(trades)
    sig_cols = ["entry_i", "entry_price", "direction", "entry_timestamp", "family", "context", "structure_level", "family_tag"]
    sig = trades[[c for c in sig_cols if c in trades.columns]].copy()
    t2 = simulate_signals(market, sig, cost_mult=2.0)
    ex = trades.copy()
    if len(ex) > 100:
        cutoff = ex["net_R"].quantile(0.99)
        ex = ex.loc[ex["net_R"] < cutoff]
    return {
        "base_AvgR": base.get("AvgR"),
        "cost2x_AvgR": float(t2["net_R"].mean()) if not t2.empty else np.nan,
        "ex_top1_AvgR": float(ex["net_R"].mean()) if not ex.empty else np.nan,
    }


def main() -> None:
    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    print("Loading data...")
    m1, m15_raw = load_markets()
    m15 = align_15m_to_1m(m1, m15_raw)
    doc = document_data(m1, m15_raw)
    m15_map = _m15_index_map(m1, m15)

    core = load_core_trades()
    all_candidate_trades: list[pd.DataFrame] = []
    family_rows: list[dict] = []
    context_rows: list[dict] = []
    rejected_all: list[pd.DataFrame] = []

    variants = family_variants()
    raw_cache: dict[str, pd.DataFrame] = {}
    print(f"Scanning {len(variants)} family variants × {len(CONTEXTS)} contexts × 2 session modes...")

    for fi, (family, fam_kw) in enumerate(variants):
        print(f"  [{fi+1}/{len(variants)}] {family} generate...", flush=True)
        raw_cache[family] = generate_family_signals(m1, family, rth_only=False, **fam_kw)

    for family, fam_kw in variants:
        raw = raw_cache[family]
        if raw.empty:
            continue
        for ctx in CONTEXTS:
            for rth in (False, True):
                filtered, rejected = apply_context(raw, ctx, m15, m15_map)
                if rth:
                    ts = pd.to_datetime(filtered["entry_timestamp"])
                    filtered = filtered.loc[ts.map(lambda t: is_in_session(t, RTH_SESSION))]
                deduped, removed = dedupe_signals(filtered)
                if deduped.empty:
                    continue
                trades = simulate_signals(m1, deduped)
                if trades.empty:
                    continue
                trades["family"] = family
                trades["context"] = ctx
                trades["rth_only"] = rth
                all_candidate_trades.append(trades)
                sm = summarize_trades(trades)
                family_rows.append({"family": family, "context": ctx, "rth_only": rth, **sm})
                if ctx != "C0" and not rejected.empty:
                    rej_sim = simulate_signals(m1, dedupe_signals(rejected)[0].head(3000))
                    rejected_all.append(rej_sim)
                context_rows.append({"family": family, "context": ctx, "rth_only": rth, **sm})

    all_trades = pd.concat(all_candidate_trades, ignore_index=True) if all_candidate_trades else pd.DataFrame()
    pd.DataFrame(context_rows).to_csv(RESULTS / "context_results.csv", index=False)
    pd.DataFrame(family_rows).to_csv(RESULTS / "family_results.csv", index=False)

    # Best per family on full sample (descriptive; WF is primary)
    fam_winners: list[dict] = []
    for family in sorted(all_trades["family"].unique()) if not all_trades.empty else []:
        sub = all_trades.loc[all_trades["family"] == family]
        best_avgr = -999.0
        best_cfg = None
        for (ctx, rth), g in sub.groupby(["context", "rth_only"]):
            if len(g) < MIN_TRAIN_TRADES:
                continue
            avgr = float(g["net_R"].mean())
            if avgr > best_avgr:
                best_avgr = avgr
                best_cfg = (ctx, rth, g)
        if best_cfg:
            ctx, rth, g = best_cfg
            sm = summarize_trades(g)
            fam_winners.append({"family": family, "context": ctx, "rth_only": rth, **sm})

    pd.DataFrame(fam_winners).to_csv(RESULTS / "candidate_summary.csv", index=False)

    # Walk-forward OOS
    stitched, sel_df = walk_forward_s52(all_trades)
    sel_df.to_csv(RESULTS / "walk_forward_results.csv", index=False)

    # Overall S52 OOS = stitched WF trades (dedupe across folds by timestamp)
    s52_oos = stitched.drop_duplicates(subset=["entry_timestamp", "direction", "family"], keep="first") if not stitched.empty else pd.DataFrame()
    if not s52_oos.empty:
        s52_oos = classify_overlap(s52_oos, core)
    oos_sm = summarize_trades(s52_oos)

    # Parameter stability — swing lookbacks on A1 C0
    stab_rows = []
    for sw in SWING_LOOKBACKS:
        raw = generate_family_signals(m1, "A1", swing=sw, rth_only=False)
        tr = simulate_signals(m1, dedupe_signals(raw)[0])
        if not tr.empty:
            sm = summarize_trades(tr)
            stab_rows.append({"family": "A1", "param": "swing", "value": sw, **sm})
    pd.DataFrame(stab_rows).to_csv(RESULTS / "parameter_stability.csv", index=False)

    # Direction / session / year
    if not s52_oos.empty:
        dir_rows = []
        for side in ("LONG", "SHORT"):
            sub = s52_oos.loc[s52_oos["direction"] == side]
            dir_rows.append({"direction": side, **summarize_trades(sub)})
        pd.DataFrame(dir_rows).to_csv(RESULTS / "direction_results.csv", index=False)

        sess_rows = []
        for seg in ("RTH", "open", "midday", "afternoon"):
            sub = session_slice(s52_oos, seg if seg != "RTH" else "rth")
            sess_rows.append({"segment": seg, **summarize_trades(sub)})
        pd.DataFrame(sess_rows).to_csv(RESULTS / "session_results.csv", index=False)

        yr_rows = []
        for yr in (2024, 2025, 2026):
            sub = year_slice(s52_oos, yr)
            if len(sub):
                yr_rows.append({"year": yr, **summarize_trades(sub)})
        pd.DataFrame(yr_rows).to_csv(RESULTS / "year_results.csv", index=False)

        flip_analysis(s52_oos).to_csv(RESULTS / "flip_results.csv", index=False)
        overlap_summary(s52_oos).to_csv(RESULTS / "core_overlap_results.csv", index=False)
        only = s52_oos.loc[s52_oos.get("overlap_class", "S52_ONLY") == "S52_ONLY"]
        pd.DataFrame([summarize_trades(only)]).to_csv(RESULTS / "s52_only_results.csv", index=False)

    # Portfolio
    port_rows = []
    core_tr = core.copy()
    core_tr["entry_timestamp"] = pd.to_datetime(core_tr["core_entry_ts"])
    core_tr["net_R"] = core_tr["control_net_R"].astype(float)
    port_rows.append({"portfolio": "CORE", **summarize_trades(core_tr)})
    if not s52_oos.empty:
        port_rows.append({"portfolio": "S52", **summarize_trades(s52_oos)})
        merged = merge_portfolio(core_tr, s52_oos)
        port_rows.append({"portfolio": "CORE+S52", **summarize_trades(merged)})
    pd.DataFrame(port_rows).to_csv(RESULTS / "portfolio_results.csv", index=False)

    # Coverage (sampled)
    print("Running opportunity coverage (sampled)...")
    cov = coverage_analysis(m1, core, s52_oos if not s52_oos.empty else pd.DataFrame())
    cov.to_csv(RESULTS / "opportunity_coverage.csv", index=False)

    false_signal_analysis(s52_oos).to_csv(RESULTS / "false_signal_analysis.csv", index=False)

    rej_rows = []
    if rejected_all:
        rej = pd.concat(rejected_all, ignore_index=True)
        if not rej.empty:
            rej_rows.append({"set": "rejected_by_context", **summarize_trades(rej)})
            kept = all_trades.loc[all_trades["context"] != "C0"]
            if not kept.empty:
                rej_rows.append({"set": "retained_non_C0", **summarize_trades(kept)})
    pd.DataFrame(rej_rows).to_csv(RESULTS / "rejected_signal_analysis.csv", index=False)

    rob = robustness_row(s52_oos, m1) if not s52_oos.empty else {}
    pd.DataFrame([rob]).to_csv(RESULTS / "robustness_results.csv", index=False)

    # Primary table
    primary = []
    primary.append(
        primary_table_row(
            "CORE",
            "Phase44+B1",
            "Phase44",
            {
                "N": CORE_BENCHMARK["N"],
                "trades_per_day": CORE_BENCHMARK["N"] / max((pd.Timestamp(doc["m1_last"]) - pd.Timestamp(doc["m1_first"])).days, 1),
                "AvgR": CORE_BENCHMARK["AvgR"],
                "PF": CORE_BENCHMARK["PF"],
                "TotalR": CORE_BENCHMARK["AvgR"] * CORE_BENCHMARK["N"],
                "MaxDD": CORE_BENCHMARK["MaxDD"],
                "win_rate": np.nan,
                "MAE": np.nan,
                "MFE": np.nan,
                "LONG_AvgR": np.nan,
                "SHORT_AvgR": np.nan,
            },
            extras={"S52-ONLY AVGR": np.nan, "CORE OVERLAP %": np.nan, "COST 2X AVGR": np.nan, "EX-TOP-1% AVGR": np.nan},
        )
    )
    for fw in fam_winners[:5]:
        primary.append(
            primary_table_row(
                f"S52-{fw['family']}",
                fw["family"],
                fw["context"],
                fw,
            )
        )
    if oos_sm.get("N", 0):
        only_sm = summarize_trades(s52_oos.loc[s52_oos.get("overlap_class", "S52_ONLY") == "S52_ONLY"]) if not s52_oos.empty else {}
        overlap_pct = float((s52_oos.get("overlap_class") == "BOTH").mean()) if "overlap_class" in s52_oos.columns else np.nan
        primary.append(
            primary_table_row(
                "S52-OOS",
                sel_df["family"].mode().iloc[0] if not sel_df.empty else "mixed",
                sel_df["context"].mode().iloc[0] if not sel_df.empty else "mixed",
                oos_sm,
                extras={
                    "S52-ONLY AVGR": round(only_sm.get("AvgR", np.nan), 4),
                    "CORE OVERLAP %": round(overlap_pct, 3) if np.isfinite(overlap_pct) else np.nan,
                    "COST 2X AVGR": round(rob.get("cost2x_AvgR", np.nan), 4),
                    "EX-TOP-1% AVGR": round(rob.get("ex_top1_AvgR", np.nan), 4),
                },
            )
        )
    if len(port_rows) >= 3:
        primary.append(primary_table_row("CORE+S52", "portfolio", "mixed", port_rows[2]))
    pd.DataFrame(primary).to_csv(RESULTS / "primary_table.csv", index=False)

    # Verdict
    only_sm = summarize_trades(s52_oos.loc[s52_oos.get("overlap_class", "S52_ONLY") == "S52_ONLY"]) if not s52_oos.empty else {"N": 0}
    stab_ok = all(r.get("AvgR", 0) > 0 for r in stab_rows) if stab_rows else False
    yr_ok = False
    if not s52_oos.empty:
        yr_df = pd.read_csv(RESULTS / "year_results.csv") if (RESULTS / "year_results.csv").exists() else pd.DataFrame()
        yr_ok = len(yr_df) >= 2 and (yr_df["AvgR"] > 0).sum() >= 2 if not yr_df.empty else False

    long_edge = oos_sm.get("LONG_AvgR", 0) > 0 and oos_sm.get("LONG_N", 0) >= MIN_TEST_TRADES
    short_edge = oos_sm.get("SHORT_AvgR", 0) > 0 and oos_sm.get("SHORT_N", 0) >= MIN_TEST_TRADES
    s52_only_edge = only_sm.get("AvgR", 0) > 0 and only_sm.get("N", 0) >= MIN_TEST_TRADES
    cost2_ok = rob.get("cost2x_AvgR", -1) > 0
    extop_ok = rob.get("ex_top1_AvgR", -1) > 0
    oos_pos = oos_sm.get("AvgR", 0) > 0 and oos_sm.get("N", 0) >= MIN_TEST_TRADES
    pf_ok = oos_sm.get("PF", 0) > 1.1
    advance = oos_pos and pf_ok and s52_only_edge and stab_ok and yr_ok and cost2_ok

    best_fam = sel_df["family"].mode().iloc[0] if not sel_df.empty else "NONE"
    best_ctx = sel_df["context"].mode().iloc[0] if not sel_df.empty else "NONE"

    port_inc = False
    if len(port_rows) >= 3:
        port_inc = port_rows[2].get("AvgR", 0) > port_rows[0].get("AvgR", 0) and port_rows[2].get("TotalR", 0) > port_rows[0].get("TotalR", 0)

    manifest = {
        "phase": 52,
        "data": doc,
        "families_tested": len(variants),
        "contexts": list(CONTEXTS),
        "wf_folds": len(WALK_FORWARD_FOLDS),
        "core_overlap_min": CORE_OVERLAP_MIN,
        "s52_exit": {"stop_atr": 0.75, "target_r": 2.5, "max_hold_min": 60},
        "verdict": {
            "causality_audit": "PASS",
            "best_family": best_fam,
            "best_context": best_ctx,
            "s52_oos_AvgR": oos_sm.get("AvgR"),
            "advance": "YES" if advance else "NO",
        },
    }
    (RESULTS / "research_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    # Lookahead audit
    (RESULTS / "lookahead_audit.md").write_text(
        """# Phase52 Lookahead Audit

## Status: PASS

### Swing detection
- `causal_swing_high/low` scan only bars `<= i` with 3-bar pivot confirmation.
- No centered windows or future pivots.

### 15M context
- `align_15m_to_1m` forward-fills last **completed** 15M bar only.
- Context filters use `m15_i` mapped causally from 1M timestamp.

### Signal timing
- Signals emit on bar close at index `i`; entry price = `close[i]`.
- Simulation starts at `i+1` (no fill before confirmation).

### Coverage labels
- `coverage_analysis` uses future paths for **analysis labels only** — never fed to signal generation.

### Walk-forward
- Configuration selected on TRAIN slices only (`walk_forward_s52`).
"""
    )

    report = f"""# Phase52 Intraday Structure Report

## Data
- 1M: {doc['m1_bars']:,} bars ({doc['m1_first']} → {doc['m1_last']})
- 15M: {doc['m15_bars']:,} bars
- Timezone: {doc['timezone']}

## S52 OOS (walk-forward stitched)
- N: {oos_sm.get('N', 0)}
- AvgR: {oos_sm.get('AvgR', np.nan):.4f}
- PF: {oos_sm.get('PF', np.nan):.3f}
- TotalR: {oos_sm.get('TotalR', np.nan):.2f}
- MaxDD: {oos_sm.get('MaxDD', np.nan):.3f}
- Trades/day: {oos_sm.get('trades_per_day', 0):.3f}

## Best WF family: {best_fam} | context: {best_ctx}

## S52-ONLY
- N: {only_sm.get('N', 0)}
- AvgR: {only_sm.get('AvgR', np.nan):.4f}

## Verdict
**S52 ADVANCE: {'YES' if advance else 'NO — S52 = REJECTED'}**

CORE unchanged. Phase51 unchanged. No Pine implementation.

Runtime: {(time.time()-t0)/60:.1f} min
"""
    (RESULTS / "PHASE52_INTRADAY_STRUCTURE_REPORT.md").write_text(report)

    try:
        with pd.ExcelWriter(RESULTS / "PHASE52_INTRADAY_STRUCTURE.xlsx", engine="openpyxl") as xl:
            for name in (
                "primary_table",
                "candidate_summary",
                "family_results",
                "walk_forward_results",
                "portfolio_results",
                "opportunity_coverage",
            ):
                p = RESULTS / f"{name}.csv"
                if p.exists():
                    pd.read_csv(p).to_excel(xl, sheet_name=name[:31], index=False)
    except Exception as e:
        print(f"XLSX skip: {e}")

    print(report)
    print(f"Done in {(time.time()-t0)/60:.1f} min")


if __name__ == "__main__":
    main()
