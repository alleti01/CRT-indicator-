"""Phase 31 orchestration — daily-frequency 15m entry discovery."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from phase29.simulator import SimConfig

from .config import (
    PHASE30_EXEC,
    RESULTS,
    hold_bars,
)
from .data import load_market_15m
from .dedupe import rth_trading_dates
from .metrics import (
    classify,
    cost_stress,
    daily_distribution,
    enrich_net,
    frequency_frontier,
    monte_carlo,
    net_performance,
    optimization_grid,
    outlier_robustness,
    performance,
    simulate_all,
    success_criteria,
    trade_paths,
    walk_forward,
    yearly_results,
)
from .signals import ARCHITECTURES, build_architecture_signals


def _screen_architecture(signals: pd.DataFrame, market: pd.DataFrame) -> Dict[str, float]:
    cfg = SimConfig(
        entry_model="CURRENT",
        stop_atr=1.0,
        target_r=2.0,
        max_bars=hold_bars(60),
        management="FIXED",
    )
    sim = simulate_all(signals, market, cfg)
    filled = enrich_net(sim.loc[sim.filled])
    perf = net_performance(filled)
    daily = daily_distribution(filled, market, ts_col="entry_timestamp")
    perf["trades_day"] = daily["mean_signals_day"]
    return perf


def _direction_table(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for direction in ("Long", "Short"):
        sub = trades.loc[trades["direction"] == direction] if not trades.empty else pd.DataFrame()
        rows.append({"direction": direction, **performance(sub, col="net_R")})
    return pd.DataFrame(rows)


def _write_excel(output: Path, tables: Dict[str, pd.DataFrame]) -> None:
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for name, df in tables.items():
                sheet = name[:31]
                (df if not df.empty else pd.DataFrame({"note": ["empty"]})).to_excel(writer, sheet_name=sheet, index=False)
    except ImportError:
        pass


def run_phase31(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    (output.parent.parent / "tests").mkdir(parents=True, exist_ok=True)

    market = load_market_15m()
    cache_path = output / "_signals_cache.pkl"
    if cache_path.exists():
        with cache_path.open("rb") as fh:
            arch_signals = pickle.load(fh)
    else:
        arch_signals = build_architecture_signals(market)
        with cache_path.open("wb") as fh:
            pickle.dump(arch_signals, fh)
    grid = optimization_grid()
    full_grid_size = len(grid)
    n_combos = 0

    screen_rows = []
    all_paths: List[pd.DataFrame] = []
    wf_trades_parts: List[pd.DataFrame] = []
    wf_selection_parts: List[pd.DataFrame] = []
    wf_fold_parts: List[pd.DataFrame] = []
    stab_parts: List[pd.DataFrame] = []

    for arch in ARCHITECTURES:
        signals = arch_signals[arch]
        screen = _screen_architecture(signals, market)
        screen_rows.append({"architecture": arch, **screen})
        folds, stitched, stab = walk_forward(signals, market, grid, architecture=arch)
        n_combos += int(getattr(stitched, "attrs", {}).get("combo_count", 0))
        if not folds.empty:
            wf_fold_parts.append(folds)
        if not stitched.empty:
            wf_trades_parts.append(stitched)
        if not stab.empty:
            stab_parts.append(stab)
        if not folds.empty:
            sel = folds[
                ["architecture", "train_end", "test_end", "entry_model", "stop_atr", "target_r", "hold_minutes"]
            ].copy()
            wf_selection_parts.append(sel)

    screen_df = pd.DataFrame(screen_rows)
    screen_df.to_csv(output / "candidate_architectures.csv", index=False)

    paths_df = pd.concat(all_paths, ignore_index=True) if all_paths else pd.DataFrame()
    paths_df.to_csv(output / "candidate_trade_paths.csv", index=False)

    wf_trades = pd.concat(wf_trades_parts, ignore_index=True) if wf_trades_parts else pd.DataFrame()
    wf_trades.to_csv(output / "walk_forward_trades.csv", index=False)

    wf_selections = pd.concat(wf_selection_parts, ignore_index=True) if wf_selection_parts else pd.DataFrame()
    wf_selections.to_csv(output / "walk_forward_selections.csv", index=False)

    stab_df = pd.concat(stab_parts, ignore_index=True) if stab_parts else pd.DataFrame()
    stab_df.to_csv(output / "parameter_stability.csv", index=False)

    arch_wf_rows = []
    for arch in ARCHITECTURES:
        sub = wf_trades.loc[wf_trades["architecture"] == arch] if not wf_trades.empty else pd.DataFrame()
        perf = net_performance(sub)
        daily = daily_distribution(sub, market, ts_col="entry_timestamp")
        arch_wf_rows.append({"architecture": arch, "NetAvgR": perf["AvgR"], "NetPF": perf["PF"], **perf, **daily})
    arch_wf = pd.DataFrame(arch_wf_rows)
    frontier = frequency_frontier(arch_wf)
    frontier.to_csv(output / "frequency_quality_frontier.csv", index=False)

    if arch_wf.empty:
        best_arch = ARCHITECTURES[0]
    else:
        eligible = arch_wf.loc[(arch_wf["mean_signals_day"] >= 0.5) & (arch_wf["NetAvgR"] > 0)]
        best_arch = (
            eligible.sort_values(["NetAvgR", "NetPF", "ReturnMaxDD"], ascending=False).iloc[0]["architecture"]
            if not eligible.empty
            else arch_wf.sort_values("NetAvgR", ascending=False).iloc[0]["architecture"]
        )

    best_trades = wf_trades.loc[wf_trades["architecture"] == best_arch].copy() if not wf_trades.empty else pd.DataFrame()
    if not best_trades.empty:
        best_sig = arch_signals[best_arch]
        paths = trade_paths(best_sig, market, best_trades)
        if not paths.empty:
            paths["architecture"] = best_arch
            all_paths.append(paths)
    wf_perf = net_performance(best_trades)
    daily_best = daily_distribution(best_trades, market, ts_col="entry_timestamp")
    daily_df = pd.DataFrame([daily_best])
    daily_df.to_csv(output / "daily_signal_distribution.csv", index=False)

    yearly = yearly_results(best_trades, market)
    yearly.to_csv(output / "yearly_results.csv", index=False)

    direction = _direction_table(best_trades)
    direction.to_csv(output / "direction_results.csv", index=False)

    cost_df = cost_stress(best_trades, best_arch)
    cost_df.to_csv(output / "cost_stress.csv", index=False)

    outlier = outlier_robustness(best_trades)
    outlier.to_csv(output / "outlier_robustness.csv", index=False)

    mc = monte_carlo(best_trades)
    pd.DataFrame([mc] if mc else [{"note": "empty"}]).to_csv(output / "monte_carlo.csv", index=False)

    passed, checks = success_criteria(wf_perf, daily_best, yearly, outlier, cost_df, best_trades)
    final_class = classify(passed, wf_perf, daily_best)
    ready = passed >= 14

    baselines = {}
    for label, arch in (
        ("phase30_crt_v2", "CRT_V2_B_LEGACY_EXP6"),
        ("phase28_retest_gated", "RETEST_GATED"),
        ("bos_baseline", "BOS_ONLY"),
    ):
        sub = wf_trades.loc[wf_trades["architecture"] == arch] if not wf_trades.empty else pd.DataFrame()
        baselines[label] = net_performance(sub)

    report_lines = [
        "# Phase 31 — NQ 15M Daily-Frequency High-Quality Entry Discovery",
        "",
        "## Objective",
        "Find a 15m NQ entry architecture producing ~1–2 high-quality actionable trades per RTH day with positive net expectancy after costs.",
        "",
        "## Architectures Tested",
        ", ".join(ARCHITECTURES),
        "",
        f"Full execution grid size (reference): {full_grid_size} combos",
        f"Walk-forward fold shortlist evaluations (actual): {n_combos}",
        "",
        "## Deduplication Rule",
        "RTH-only signals; one active trade at a time; minimum 4 bars between same-direction entries; one signal per structural event_id; maximum 2 signals per RTH session day (causal cap).",
        "",
        f"## Best Signal Architecture (walk-forward stitched): **{best_arch}**",
        "",
        "### Stitched Walk-Forward (net of $14.50 RT costs)",
        f"- N = {wf_perf.get('N', 0)}",
        f"- Trades/day (mean) = {daily_best.get('mean_signals_day', 0):.3f}",
        f"- Net AvgR = {wf_perf.get('AvgR', 0):.4f}",
        f"- Net PF = {wf_perf.get('PF', 0):.3f}",
        f"- Net TotalR = {wf_perf.get('TotalR', 0):.2f}",
        f"- MaxDD = {wf_perf.get('MaxDD', 0):.2f}",
        f"- Return/MaxDD = {wf_perf.get('ReturnMaxDD', 0):.2f}",
        "",
        "## Daily Signal Distribution",
        f"- RTH days = {daily_best.get('total_rth_days', 0)}",
        f"- 0 signal days = {daily_best.get('days_0', 0)} ({daily_best.get('pct_days_0', 0)*100:.1f}%)",
        f"- 1 signal days = {daily_best.get('days_1', 0)} ({daily_best.get('pct_days_1', 0)*100:.1f}%)",
        f"- 2 signal days = {daily_best.get('days_2', 0)} ({daily_best.get('pct_days_2', 0)*100:.1f}%)",
        f"- 3+ signal days = {daily_best.get('days_3plus', 0)} ({daily_best.get('pct_days_gt2', 0)*100:.1f}%)",
        "",
        "## Baseline Comparisons (stitched WF, net)",
    ]
    for label, perf in baselines.items():
        report_lines.append(
            f"- {label}: N={perf.get('N',0)}, AvgR={perf.get('AvgR',0):.4f}, PF={perf.get('PF',0):.2f}, trades/day via arch map"
        )
    report_lines.extend(
        [
            "",
            "## Frequency / Quality Frontier",
            frontier.to_string(index=False) if not frontier.empty else "No frontier rows.",
            "",
            "## Success Criteria",
            f"Passed {passed} / 14 gates:",
        ]
    )
    for name, ok in checks:
        report_lines.append(f"- {'✓' if ok else '✗'} {name}")
    report_lines.extend(
        [
            "",
            f"## Final Classification: **{final_class}**",
            f"## READY FOR PINE: **{'YES' if ready else 'NO'}**",
            "",
            "## Most Important Finding",
        ]
    )
    if daily_best.get("mean_signals_day", 0) < 0.75 or wf_perf.get("AvgR", 0) < 0.10:
        report_lines.append(
            "At the requested daily frequency (0.75–2.0 trades/RTH day), no architecture satisfied all minimum success criteria "
            "while maintaining robust net expectancy. See frequency_quality_frontier.csv for the quality/frequency tradeoff."
        )
    else:
        report_lines.append(f"{best_arch} reached the target frequency band with net AvgR {wf_perf.get('AvgR',0):.3f}R in stitched walk-forward.")
    report_lines.append("")
    report_lines.append("## Next Step")
    if ready:
        report_lines.append("Proceed to Pine implementation with frozen walk-forward parameters.")
    else:
        report_lines.append("Do not implement Pine. Either accept lower frequency (Phase 30 CRT) or treat daily-frequency 15m entries as unsupported.")

    report_path = output / "DAILY_FREQUENCY_ENTRY_REPORT.md"
    report_path.write_text("\n".join(report_lines))

    manifest = {
        "phase": "Phase 31 — NQ 15M Daily-Frequency High-Quality Entry Discovery",
        "architectures_tested": list(ARCHITECTURES),
        "parameter_combinations_full_grid": full_grid_size,
        "parameter_combinations_wf_evaluated": n_combos,
        "deduplication": "RTH-only; one active trade; 4-bar same-direction gap; one per event_id; max 2 signals/RTH day",
        "best_architecture": best_arch,
        "stitched_walk_forward_net": wf_perf,
        "daily_distribution": daily_best,
        "baselines": baselines,
        "success_criteria_passed": passed,
        "success_criteria_total": 14,
        "checks": {k: v for k, v in checks},
        "final_classification": final_class,
        "ready_for_pine": ready,
        "monte_carlo": mc,
        "phase30_reference_exec": PHASE30_EXEC,
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    _write_excel(
        output / "DAILY_FREQUENCY_ENTRY.xlsx",
        {
            "architectures": screen_df,
            "wf_trades": wf_trades,
            "frontier": frontier,
            "daily": daily_df,
            "yearly": yearly,
            "direction": direction,
            "cost": cost_df,
            "outlier": outlier,
            "monte_carlo": pd.DataFrame([mc] if mc else []),
        },
    )

    return manifest


if __name__ == "__main__":
    run_phase31()
