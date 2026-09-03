"""Phase 33 metrics, walk-forward, and reporting."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

from phase29.config import WALK_FORWARD_FOLDS
from phase31.dedupe import dedupe_signals, rth_trading_dates
from phase31.metrics import (
    apply_costs,
    cme_session_date,
    enrich_net,
    monte_carlo,
    net_performance,
    outlier_robustness,
    performance,
    score_train,
    trade_paths,
    yearly_results,
)

from .config import ARCHITECTURE, CHART_MINUTES, WF_EXECUTION_GRID, WF_FAILURE_DEFS, hold_bars
from .entries import simulate_all_reversal
from .failure import failure_signals


def compare_failure_definitions(
    failures: pd.DataFrame,
    market: pd.DataFrame,
    *,
    entry_model: str = "BOS_RETEST",
    stop_atr: float = 0.75,
    target_r: float = 3.0,
    hold_minutes: int = 60,
) -> pd.DataFrame:
    rows = []
    for fdef in sorted(failures["failure_definition"].unique()):
        sig = failure_signals(failures, fdef)
        sig = dedupe_signals(sig, market, max_hold_bars=hold_bars(hold_minutes))
        cfg = {
            "entry_model": entry_model,
            "stop_atr": stop_atr,
            "target_r": target_r,
            "max_bars": hold_bars(hold_minutes),
            "management": "FIXED",
        }
        sim = simulate_all_reversal(sig, market, cfg)
        filled = enrich_net(sim.loc[sim.filled])
        unfilled = int((~sim.filled).sum())
        perf = net_performance(filled)
        rows.append(
            {
                "failure_definition": fdef,
                "signals": len(sig),
                "filled": len(filled),
                "unfilled": unfilled,
                "fill_rate": len(filled) / len(sig) if len(sig) else 0.0,
                **{f"net_{k}": v for k, v in perf.items()},
            }
        )
    return pd.DataFrame(rows)


def compare_entry_models(
    failures: pd.DataFrame,
    market: pd.DataFrame,
    failure_definition: str,
    *,
    stop_atr: float = 0.75,
    target_r: float = 3.0,
    hold_minutes: int = 60,
) -> pd.DataFrame:
    sig = dedupe_signals(failure_signals(failures, failure_definition), market, max_hold_bars=hold_bars(hold_minutes))
    rows = []
    for entry in ("CONFIRM_CLOSE", "NEXT_CLOSE", "BOS_RETEST", "RECLAIM_RETEST"):
        cfg = {
            "entry_model": entry,
            "stop_atr": stop_atr,
            "target_r": target_r,
            "max_bars": hold_bars(hold_minutes),
            "management": "FIXED",
        }
        sim = simulate_all_reversal(sig, market, cfg)
        filled = enrich_net(sim.loc[sim.filled])
        perf = net_performance(filled)
        rows.append(
            {
                "failure_definition": failure_definition,
                "entry_model": entry,
                "signals": len(sig),
                "filled": len(filled),
                "unfilled": int((~sim.filled).sum()),
                "fill_rate": len(filled) / len(sig) if len(sig) else 0.0,
                **{f"net_{k}": v for k, v in perf.items()},
            }
        )
    return pd.DataFrame(rows)


def precompute_simulations(
    signal_cache: Dict[str, pd.DataFrame],
    market: pd.DataFrame,
) -> Dict[tuple, pd.DataFrame]:
    cache: Dict[tuple, pd.DataFrame] = {}
    total = len(signal_cache) * len(WF_EXECUTION_GRID)
    done = 0
    for fdef, sig in signal_cache.items():
        if sig.empty:
            continue
        for row in WF_EXECUTION_GRID:
            cfg = dict(row)
            cfg["max_bars"] = hold_bars(int(row["hold_minutes"]))
            key = (fdef, cfg["entry_model"], cfg["stop_atr"], cfg["target_r"], cfg["max_bars"])
            cache[key] = simulate_all_reversal(sig, market, cfg)
            done += 1
            if done % 24 == 0:
                print(f"Phase33 precompute {done}/{total}", flush=True)
    return cache


def walk_forward_reversal(
    failures: pd.DataFrame,
    market: pd.DataFrame,
    *,
    signal_cache: Dict[str, pd.DataFrame] | None = None,
    sim_cache: Dict[tuple, pd.DataFrame] | None = None,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tz = failures["confirm_timestamp"].dt.tz if not failures.empty else None
    fold_rows, stitched_parts, selections = [], [], []
    combo_count = 0
    if signal_cache is None:
        signal_cache = {
            fdef: dedupe_signals(failure_signals(failures, fdef), market)
            for fdef in WF_FAILURE_DEFS
            if not failure_signals(failures, fdef).empty
        }
    if sim_cache is None:
        sim_cache = precompute_simulations(signal_cache, market)
    combo_count = len(sim_cache) * len(WALK_FORWARD_FOLDS)
    for train_start, train_end, test_start, test_end in WALK_FORWARD_FOLDS:
        best_score, best_sel = -999.0, None
        rth_days = max(
            1,
            len(rth_trading_dates(market.loc[pd.Timestamp(train_start, tz=tz) : pd.Timestamp(train_end, tz=tz)])),
        )
        for fdef in signal_cache:
            train_sig = signal_cache[fdef].loc[
                (signal_cache[fdef].entry_timestamp >= pd.Timestamp(train_start, tz=tz))
                & (signal_cache[fdef].entry_timestamp <= pd.Timestamp(train_end, tz=tz))
            ]
            test_sig = signal_cache[fdef].loc[
                (signal_cache[fdef].entry_timestamp >= pd.Timestamp(test_start, tz=tz))
                & (signal_cache[fdef].entry_timestamp <= pd.Timestamp(test_end, tz=tz))
            ]
            if len(train_sig) < 20 or len(test_sig) < 5:
                continue
            train_ids = set(train_sig.signal_id)
            for row in WF_EXECUTION_GRID:
                cfg = dict(row)
                cfg["max_bars"] = hold_bars(int(row["hold_minutes"]))
                key = (fdef, cfg["entry_model"], cfg["stop_atr"], cfg["target_r"], cfg["max_bars"])
                sim = sim_cache[key]
                train_sim = sim.loc[sim.signal_id.isin(train_ids)]
                filled = enrich_net(train_sim.loc[train_sim.filled])
                td = len(filled) / rth_days
                sc = score_train(filled, trades_day=td)
                if sc > best_score:
                    best_score = sc
                    best_sel = {
                        "failure_definition": fdef,
                        **cfg,
                        "train_signals": len(train_sig),
                        "test_signals": len(test_sig),
                    }
        if best_sel is None:
            continue
        test_sig = signal_cache[best_sel["failure_definition"]].loc[
            (signal_cache[best_sel["failure_definition"]].entry_timestamp >= pd.Timestamp(test_start, tz=tz))
            & (signal_cache[best_sel["failure_definition"]].entry_timestamp <= pd.Timestamp(test_end, tz=tz))
        ]
        test_ids = set(test_sig.signal_id)
        key = (
            best_sel["failure_definition"],
            best_sel["entry_model"],
            best_sel["stop_atr"],
            best_sel["target_r"],
            best_sel["max_bars"],
        )
        test_sim = sim_cache[key].loc[sim_cache[key].signal_id.isin(test_ids)]
        filled = enrich_net(test_sim.loc[test_sim.filled])
        filled["architecture"] = ARCHITECTURE
        filled["failure_definition"] = best_sel["failure_definition"]
        filled["fold_test_end"] = test_end
        stitched_parts.append(filled)
        fold_rows.append(
            {
                "architecture": ARCHITECTURE,
                "train_end": train_end,
                "test_end": test_end,
                **performance(filled, col="net_R"),
                **{k: best_sel[k] for k in ("failure_definition", "entry_model", "stop_atr", "target_r", "hold_minutes", "management")},
            }
        )
        selections.append(best_sel | {"architecture": ARCHITECTURE, "test_end": test_end})
    folds = pd.DataFrame(fold_rows)
    stitched = pd.concat(stitched_parts, ignore_index=True) if stitched_parts else pd.DataFrame()
    sel = pd.DataFrame(selections)
    stab = []
    if not sel.empty:
        for col in ("failure_definition", "entry_model", "stop_atr", "target_r", "hold_minutes"):
            for val, cnt in sel[col].value_counts().items():
                stab.append({"architecture": ARCHITECTURE, "parameter": col, "value": val, "count": int(cnt), "folds": len(sel)})
    stitched.attrs["combo_count"] = combo_count
    return folds, stitched, sel, pd.DataFrame(stab)


def failure_strength_monotonicity(trades: pd.DataFrame, strength: pd.DataFrame) -> Tuple[str, pd.DataFrame]:
    if trades.empty or strength.empty:
        return "NO", pd.DataFrame()
    merged = trades.merge(strength, left_on="event_id", right_on="failure_event_id", how="left")
    merged = enrich_net(merged)
    merged["body_ratio_q"] = pd.qcut(merged["body_ratio"], 4, duplicates="drop")
    rows = []
    for q, g in merged.groupby("body_ratio_q", observed=True):
        rows.append({"bucket": str(q), "N": len(g), **performance(g, col="net_R")})
    qdf = pd.DataFrame(rows)
    if len(qdf) < 2:
        return "NO", qdf
    avgs = qdf["AvgR"].to_numpy()
    mono = bool(np.all(np.diff(avgs) >= -0.02))
    return ("YES" if mono and avgs[-1] > avgs[0] else "NO"), qdf


def cost_stress(trades: pd.DataFrame, architecture: str) -> pd.DataFrame:
    rows = []
    for mult in (1.0, 1.5, 2.0):
        net = apply_costs(trades, multiplier=mult)
        rows.append({"architecture": architecture, "cost_multiplier": mult, **performance(trades.assign(net_R=net), col="net_R")})
    return pd.DataFrame(rows)


def direction_table(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for direction in ("Long", "Short"):
        sub = trades.loc[trades["direction"] == direction] if not trades.empty else pd.DataFrame()
        rows.append({"direction": direction, **performance(sub, col="net_R")})
    return pd.DataFrame(rows)


def displacement_direction_table(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for disp_dir, rev in (("Short", "Long"), ("Long", "Short")):
        sub = trades.loc[trades["displacement_direction"] == disp_dir] if "displacement_direction" in trades.columns else pd.DataFrame()
        label = f"BEARISH_DISP_{rev}_REVERSAL" if disp_dir == "Short" else f"BULLISH_DISP_{rev}_REVERSAL"
        rows.append({"segment": label, "displacement_direction": disp_dir, "reversal_direction": rev, **performance(sub, col="net_R")})
    return pd.DataFrame(rows)


def phase31_interaction(
    phase31_trades: pd.DataFrame,
    reversal_failures: pd.DataFrame,
    market: pd.DataFrame,
) -> pd.DataFrame:
    if phase31_trades.empty or reversal_failures.empty:
        return pd.DataFrame()
    p31 = phase31_trades.copy()
    p31["entry_timestamp"] = pd.to_datetime(p31["entry_timestamp"], utc=True)
    p31["exit_timestamp"] = pd.to_datetime(p31["exit_timestamp"], utc=True)
    rev = reversal_failures.copy()
    rev["confirm_timestamp"] = pd.to_datetime(rev["confirm_timestamp"], utc=True)
    rows = []
    for policy in ("IGNORE", "EXIT_ON_CONFIRMED_REVERSAL", "EXIT_AND_FLIP"):
        adjusted = []
        flips = 0
        for _, tr in p31.iterrows():
            r = tr.copy()
            active = (rev.displacement_timestamp == tr.get("entry_timestamp")) | (
                (rev.confirm_timestamp >= tr.entry_timestamp) & (rev.confirm_timestamp <= tr.exit_timestamp)
            )
            opp = rev.loc[active & (rev.reversal_direction != tr.direction)]
            if policy != "IGNORE" and not opp.empty:
                conf_ts = opp.iloc[0]["confirm_timestamp"]
                if conf_ts > tr.entry_timestamp and conf_ts < tr.exit_timestamp:
                    r["exit_timestamp"] = conf_ts
                    r["exit_reason"] = "REVERSAL_" + policy
                    flips += 1 if policy == "EXIT_AND_FLIP" else 0
            adjusted.append(r)
        adj = pd.DataFrame(adjusted)
        perf = net_performance(adj)
        rows.append({"policy": policy, "flip_count": flips, **perf})
    return pd.DataFrame(rows)


def combined_system(
    phase31_trades: pd.DataFrame,
    phase33_trades: pd.DataFrame,
    *,
    policy: str = "INDEPENDENT",
) -> pd.DataFrame:
    rows = []
    p31 = enrich_net(phase31_trades.copy()) if not phase31_trades.empty else pd.DataFrame()
    p33 = enrich_net(phase33_trades.copy()) if not phase33_trades.empty else pd.DataFrame()
    for col in ("entry_timestamp", "exit_timestamp"):
        if not p31.empty and col in p31.columns:
            p31[col] = pd.to_datetime(p31[col], utc=True)
        if not p33.empty and col in p33.columns:
            p33[col] = pd.to_datetime(p33[col], utc=True)
    for pol in ("INDEPENDENT", "EXIT_ON_CONFIRMED_REVERSAL", "EXIT_AND_FLIP"):
        if pol == "INDEPENDENT":
            combined = pd.concat([p31, p33], ignore_index=True) if not p31.empty or not p33.empty else pd.DataFrame()
        else:
            combined = pd.concat([p31, p33], ignore_index=True)
        combined = combined.sort_values("entry_timestamp") if not combined.empty and "entry_timestamp" in combined.columns else combined
        overlap = 0
        if not p31.empty and not p33.empty:
            for _, t33 in p33.iterrows():
                conflict = p31.loc[
                    (p31.direction != t33.direction)
                    & (p31.entry_timestamp <= t33.entry_timestamp)
                    & (p31.exit_timestamp >= t33.entry_timestamp)
                ]
                overlap += len(conflict)
        perf = net_performance(combined)
        daily = len(combined) / 2188 if len(combined) else 0.0
        rows.append({"policy": pol, "overlap_conflicts": overlap, "trades_day": daily, **perf})
    return pd.DataFrame(rows)


def success_criteria_phase33(
    wf: Dict[str, float],
    yearly: pd.DataFrame,
    outlier: pd.DataFrame,
    cost: pd.DataFrame,
    mc: Dict[str, float],
    mono: str,
) -> Tuple[int, List[Tuple[str, bool]], str]:
    checks: List[Tuple[str, bool]] = []
    checks.append(("N>=500", wf.get("N", 0) >= 500))
    checks.append(("Net AvgR>=0.15", wf.get("AvgR", -9) >= 0.15))
    checks.append(("Net PF>=1.30", wf.get("PF", 0) >= 1.30))
    checks.append(("Net TotalR>0", wf.get("TotalR", -9) > 0))
    if not yearly.empty and set(yearly.year.astype(int)) >= {2024, 2025}:
        recent = yearly.loc[yearly.year.isin([2024, 2025, 2026])]
        checks.append(("2024-2026 positive", bool((recent["TotalR"] > 0).all()) if len(recent) else False))
    else:
        checks.append(("2024-2026 positive", False))
    c15 = cost.loc[cost.cost_multiplier == 1.5] if not cost.empty else pd.DataFrame()
    c20 = cost.loc[cost.cost_multiplier == 2.0] if not cost.empty else pd.DataFrame()
    checks.append(("1.5x cost positive", bool(len(c15) and c15.iloc[0]["AvgR"] > 0)))
    checks.append(("2.0x cost positive", bool(len(c20) and c20.iloc[0]["AvgR"] > 0)))
    ex1 = outlier.loc[outlier.scenario == "exclude_top1pct"] if not outlier.empty else pd.DataFrame()
    checks.append(("ex-top1% positive", bool(len(ex1) and ex1.iloc[0]["AvgR"] > 0)))
    checks.append(("MC P>0 >= 95%", mc.get("P_terminal_R_gt_0", 0) >= 0.95))
    checks.append(("failure strength monotonic", mono == "YES"))
    passed = sum(1 for _, ok in checks if ok)
    if passed >= 8 and wf.get("AvgR", 0) >= 0.20 and wf.get("PF", 0) >= 1.40:
        cls = "A"
    elif passed >= 6 and wf.get("AvgR", 0) >= 0.15 and wf.get("PF", 0) >= 1.30:
        cls = "B"
    elif wf.get("TotalR", 0) > 0:
        cls = "C"
    else:
        cls = "D"
    return passed, checks, cls
