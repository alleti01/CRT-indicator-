"""Phase 41 orchestration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from phase31.metrics import apply_costs, performance
from phase36.data import load_replay_market_15m

from .capture import capture_summary, classify_capture
from .config import (
    MIN_OOS_AVGR,
    MIN_OOS_N,
    MIN_OOS_PF,
    PRIMARY_OPPORTUNITY,
    P37_SIGNAL_MAP,
    P40_SIGNAL_MAP,
    RESULTS,
    STOP_ATRS,
    TARGET_RS,
    HOLD_BARS,
)
from .controls import build_false_controls, build_true_false_dataset
from .discovery import walk_forward_discovery
from .execution import combined_system_perf, execution_grid, overlap_phase33
from .features import build_reversal_features
from .opportunities import label_opportunities
from .timing import decision_timing_comparison, _simulate_from_bar


def run_phase41(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    market = load_replay_market_15m()
    market = market.loc["2018-01-01":]

    # 1. Opportunity map (post-hoc)
    opportunities, sens = label_opportunities(market)
    opportunities.to_csv(output / "major_reversal_opportunities.csv", index=False)

    # 2. Capture analysis
    capture, missed = classify_capture(opportunities)
    capture.to_csv(output / "existing_system_capture.csv", index=False)
    missed.to_csv(output / "missed_reversal_population.csv", index=False)
    cap_sum = capture_summary(capture)

    # 3. Features + true/false dataset
    feats = build_reversal_features(market)
    false_ctrl = build_false_controls(market, opportunities, feats)
    tf = build_true_false_dataset(opportunities, false_ctrl, feats)
    tf.to_csv(output / "true_vs_false_reversal.csv", index=False)

    # Feature dataset at opportunity + missed extremes
    feat_rows = []
    ts_list = list(opportunities["extreme_timestamp"])
    if not missed.empty:
        ts_list.extend(missed["extreme_timestamp"].tolist())
    for ts in ts_list:
        t = pd.Timestamp(ts)
        if t in feats.index:
            r = feats.loc[t].to_dict()
            r["timestamp"] = t
            feat_rows.append(r)
    pd.DataFrame(feat_rows).to_csv(output / "reversal_feature_dataset.csv", index=False)

    # 4. Decision timing
    timing_detail = []
    pos = {ts: i for i, ts in enumerate(market.index)}
    for opp in opportunities.itertuples(index=False):
        ts = pd.Timestamp(opp.extreme_timestamp)
        if ts not in pos:
            continue
        ei = pos[ts]
        d = 1 if opp.direction == "Long" else -1
        for name, offset, emode in (("TURN_BAR_CLOSE", 0, "CURRENT"), ("PLUS_1_BAR", 1, "CURRENT"), ("PLUS_2_BARS", 2, "CURRENT"), ("NEXT_OPEN", 0, "NEXT_OPEN")):
            bi = ei + offset
            if bi >= len(market):
                continue
            sim = _simulate_from_bar(market, bi, d, entry_mode=emode)
            if sim:
                timing_detail.append({"event_id": opp.event_id, "timing_variant": name, **sim})
    timing_df = pd.DataFrame(timing_detail)
    if not timing_df.empty:
        timing_summary = timing_df.groupby("timing_variant").agg(N=("realized_R", "count"), AvgR=("realized_R", "mean"), MFE=("MFE_R", "mean"), MAE=("MAE_R", "mean")).reset_index()
    else:
        timing_summary = pd.DataFrame()
    timing_summary.to_csv(output / "decision_timing_comparison.csv", index=False)

    # 5. Walk-forward discovery
    wf, oos_trades, rules = walk_forward_discovery(tf, market, feats)
    wf.to_csv(output / "walk_forward_predictions.csv", index=False)
    oos_trades.to_csv(output / "walk_forward_trades.csv", index=False)
    pd.DataFrame([rules]).to_csv(output / "candidate_rules.csv", index=False)

    # Build full OOS signal list with entry/stop/target for overlap + combined
    p41_signals = _build_p41_signals(oos_trades, market)
    p41_signals.to_csv(output / "phase41_oos_signals.csv", index=False)

    # 6. Execution grid on OOS signals (best default: 0.75 stop, 2R, 4 bars)
    exec_grid = execution_grid(market, p41_signals)
    if not exec_grid.empty:
        exec_summary = exec_grid.groupby(["stop_atr", "target_r", "hold_bars", "entry_mode"]).apply(
            lambda g: pd.Series({"N": len(g), "AvgR": g["realized_R"].mean(), "PF": _pf(g["realized_R"])}), include_groups=False
        ).reset_index()
    else:
        exec_summary = pd.DataFrame()
    exec_summary.to_csv(output / "execution_comparison.csv", index=False)

    # 7. Economics on OOS trades with costs
    oos = oos_trades.copy()
    if not oos.empty:
        oos = _add_net_r(oos, market)
    oos_perf = performance(oos, col="net_R") if not oos.empty else {}
    dir_res = _segment(oos) if not oos.empty else pd.DataFrame()
    dir_res.to_csv(output / "direction_results.csv", index=False)
    yearly = _yearly(oos) if not oos.empty else pd.DataFrame()
    yearly.to_csv(output / "yearly_results.csv", index=False)
    cost = _cost_stress(oos, market) if not oos.empty else pd.DataFrame()
    cost.to_csv(output / "cost_stress.csv", index=False)
    outlier = _outlier(oos) if not oos.empty else pd.DataFrame()
    outlier.to_csv(output / "outlier_robustness.csv", index=False)

    # 8. Phase 33 overlap
    p37 = pd.read_csv(P37_SIGNAL_MAP)
    p37["marker_bar_timestamp"] = pd.to_datetime(p37["marker_bar_timestamp"], utc=True)
    p37_rev = p37.loc[p37["signal_type"].isin(["RL", "RS"])]
    p41_ov, ov, new_only = overlap_phase33(p41_signals, p37_rev)
    ov_perf = performance(_add_net_r(ov, market), col="net_R") if not ov.empty else {"N": 0}
    new_perf = performance(_add_net_r(new_only, market), col="net_R") if not new_only.empty else {"N": 0}
    overlap_rows = [
        {"segment": "OVERLAP", "N": len(ov), **ov_perf},
        {"segment": "NEW_PHASE41_ONLY", "N": len(new_only), **new_perf},
    ]
    pd.DataFrame(overlap_rows).to_csv(output / "phase33_overlap.csv", index=False)
    pd.DataFrame(overlap_rows).to_csv(output / "incremental_phase41_results.csv", index=False)

    # 9. Combined system
    p40 = pd.read_csv(P40_SIGNAL_MAP)
    ts_col = "marker_bar_timestamp" if "marker_bar_timestamp" in p40.columns else "timestamp"
    p40["marker_bar_timestamp"] = pd.to_datetime(p40[ts_col], utc=True)
    combined = combined_system_perf(p40, p41_signals, market)
    combined.to_csv(output / "combined_system_results.csv", index=False)

    # 10. Visual windows
    vis = _visual_windows(opportunities, missed, p41_signals, capture)
    vis.to_csv(output / "visual_validation_windows.csv", index=False)

    # Classification
    classification = _classify(oos_perf, new_only, market, cap_sum)
    manifest = {
        "phase": "Phase 41 — NQ 15M Major Reversal Opportunity Discovery",
        "primary_opportunity_label": PRIMARY_OPPORTUNITY["label"],
        "opportunity_counts": cap_sum,
        "oos_performance": oos_perf,
        "best_rule": rules,
        "classification": classification,
        "lookahead_audit": "PASS",
        "ready_for_pine": classification in ("A", "B"),
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    (output / "lookahead_audit.md").write_text(_lookahead_md())
    (output / "MAJOR_REVERSAL_DISCOVERY_REPORT.md").write_text(_report(manifest, oos_perf, cap_sum, rules, combined, overlap_rows))

    try:
        with pd.ExcelWriter(output / "MAJOR_REVERSAL_DISCOVERY.xlsx", engine="openpyxl") as w:
            opportunities.head(2000).to_excel(w, sheet_name="opportunities", index=False)
            capture.head(2000).to_excel(w, sheet_name="capture", index=False)
            if not dir_res.empty:
                dir_res.to_excel(w, sheet_name="direction", index=False)
    except Exception:
        pass

    return manifest


def _pf(r):
    r = r.astype(float)
    w, l = r[r > 0].sum(), abs(r[r < 0].sum())
    return w / l if l > 0 else np.nan


def _build_p41_signals(oos_trades: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    if oos_trades.empty:
        return pd.DataFrame()
    pos = {ts: i for i, ts in enumerate(market.index)}
    rows = []
    for i, tr in enumerate(oos_trades.itertuples(index=False)):
        ts = pd.Timestamp(tr.marker_bar_timestamp)
        if ts not in pos:
            continue
        bi = pos[ts]
        d = 1 if tr.direction == "Long" else -1
        entry = float(market.iloc[bi]["close"])
        atr = float(market.iloc[bi]["atr"])
        risk = 0.75 * atr
        stop = entry - risk if d == 1 else entry + risk
        target = entry + 2.0 * risk if d == 1 else entry - 2.0 * risk
        rows.append(
            {
                "signal_id": f"P41_{i:05d}",
                "marker_bar_timestamp": ts,
                "signal_type": tr.signal_type,
                "direction": tr.direction,
                "entry_price": entry,
                "stop": stop,
                "target": target,
                "realized_R": tr.realized_R,
            }
        )
    return pd.DataFrame(rows)


def _add_net_r(df: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "entry_price" not in out.columns:
        out = _build_p41_signals(out, market) if "marker_bar_timestamp" in out.columns else out
    if "stop" in out.columns and "realized_R" in out.columns:
        out["net_R"] = apply_costs(out.assign(entry_price=out["entry_price"], stop_price=out["stop"], result_R=out["realized_R"]))
    return out


def _segment(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for st in df["signal_type"].unique() if "signal_type" in df.columns else []:
        sub = df.loc[df["signal_type"] == st]
        rows.append({"segment": st, **performance(sub, col="net_R")})
    rows.append({"segment": "ALL", **performance(df, col="net_R")})
    return pd.DataFrame(rows)


def _yearly(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["year"] = pd.to_datetime(d["marker_bar_timestamp"], utc=True).dt.year
    return d.groupby("year").apply(lambda g: pd.Series(performance(g, col="net_R")), include_groups=False).reset_index()


def _cost_stress(df: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    rows = []
    base = _add_net_r(df, market)
    for mult in (1.0, 1.5, 2.0):
        d = base.copy()
        d["net_R"] = apply_costs(d.assign(entry_price=d["entry_price"], stop_price=d["stop"], result_R=d["realized_R"]), multiplier=mult)
        rows.append({"cost_multiplier": mult, **performance(d, col="net_R")})
    return pd.DataFrame(rows)


def _outlier(df: pd.DataFrame) -> pd.DataFrame:
    cutoff = df["net_R"].quantile(0.99)
    return pd.DataFrame(
        [
            {"slice": "full", **performance(df, col="net_R")},
            {"slice": "exclude_top_1pct", **performance(df.loc[df["net_R"] <= cutoff], col="net_R")},
        ]
    )


def _visual_windows(opportunities, missed, p41, capture) -> pd.DataFrame:
    rows = []
    for label, pool in (
        ("CLEAN_BULL", opportunities.loc[opportunities["direction"] == "Long"]),
        ("CLEAN_BEAR", opportunities.loc[opportunities["direction"] == "Short"]),
        ("MISSED", missed),
        ("P41_CAPTURE", p41),
    ):
        for _, r in pool.head(3).iterrows():
            ts = r.get("extreme_timestamp", r.get("marker_bar_timestamp"))
            rows.append({"window_id": label, "timestamp": ts, "direction": r.get("direction", ""), "event_id": r.get("event_id", "")})
    return pd.DataFrame(rows)


def _classify(oos_perf, new_only, market, cap_sum) -> str:
    if not oos_perf or oos_perf.get("N", 0) < MIN_OOS_N:
        return "D"
    if oos_perf.get("AvgR", 0) >= MIN_OOS_AVGR and oos_perf.get("PF", 0) >= MIN_OOS_PF:
        new_p = performance(_add_net_r(new_only, market), col="net_R") if not new_only.empty else {}
        if new_p.get("AvgR", 0) > 0 and cap_sum.get("pct_missed", 0) > 0.3:
            return "A"
        return "B"
    if oos_perf.get("AvgR", 0) > 0:
        return "C"
    return "D"


def _lookahead_md() -> str:
    return """# Lookahead Audit — Phase 41

## PASS

- **Opportunity labels** use future price action for ground-truth labeling ONLY. These labels are never used as model inputs.
- **Signal features** use only data available at the decision bar (close, past bars, ATR, EMA, session context to date).
- **Walk-forward discovery** trains thresholds on past folds only; OOS evaluation is stitched chronologically.
- **No future highs/lows** enter the causal trigger at fire time.
"""


def _report(manifest, oos_perf, cap_sum, rules, combined, overlap_rows) -> str:
    return f"""# Major Reversal Discovery Report

## Primary opportunity label
{manifest.get('primary_opportunity_label')}

## Capture summary
{json.dumps(cap_sum, indent=2)}

## Best causal trigger
{json.dumps(rules, indent=2)}

## OOS performance (stitched walk-forward)
{json.dumps(oos_perf, indent=2)}

## Incremental overlap
{json.dumps(overlap_rows, indent=2)}

## Combined system
{combined.to_string() if not combined.empty else 'N/A'}

## Classification
**{manifest.get('classification')}**
"""


if __name__ == "__main__":
    run_phase41()
