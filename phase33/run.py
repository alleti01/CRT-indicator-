"""Phase 33 orchestration — displacement failure / reversal discovery."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import pandas as pd

from phase31.data import load_market_15m
from phase31.dedupe import dedupe_signals, rth_trading_dates
from phase31.metrics import daily_distribution, net_performance, trade_paths
from .displacements import precompute_opposite_bos, scan_displacements
from .failure import (
    build_failure_events,
    build_failure_strength,
    classify_continuation_vs_failure,
    failure_signals,
)
from .config import ARCHITECTURE, PHASE31_BENCHMARK, PHASE31_WF_TRADES, RESULTS, WF_FAILURE_DEFS
from .metrics import (
    combined_system,
    compare_entry_models,
    compare_failure_definitions,
    cost_stress,
    direction_table,
    displacement_direction_table,
    failure_strength_monotonicity,
    monte_carlo,
    outlier_robustness,
    phase31_interaction,
    precompute_simulations,
    success_criteria_phase33,
    walk_forward_reversal,
    yearly_results,
)


def _write_excel(output: Path, tables: Dict[str, pd.DataFrame]) -> None:
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for name, df in tables.items():
                sheet = name[:31]
                (df if not df.empty else pd.DataFrame({"note": ["empty"]})).to_excel(
                    writer, sheet_name=sheet, index=False
                )
    except ImportError:
        pass


def run_phase33(*, output: Path = RESULTS) -> Dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    (Path(__file__).resolve().parents[0] / "tests").mkdir(parents=True, exist_ok=True)

    market = load_market_15m()
    displacements = scan_displacements(market)
    bos_events, _ = precompute_opposite_bos(market)
    failures = build_failure_events(displacements, market, bos_events)
    continuation = classify_continuation_vs_failure(displacements, failures, market)
    strength = build_failure_strength(failures, market, displacements)

    failures.to_csv(output / "failure_events.csv", index=False)
    continuation.to_csv(output / "continuation_vs_failure.csv", index=False)
    strength.to_csv(output / "failure_strength.csv", index=False)

    fail_cmp = compare_failure_definitions(failures, market)
    fail_cmp.to_csv(output / "failure_definition_comparison.csv", index=False)
    best_fail = fail_cmp.sort_values(["net_AvgR", "net_PF"], ascending=False).iloc[0]["failure_definition"] if not fail_cmp.empty else "E_MID_BOS"
    entry_cmp = compare_entry_models(failures, market, str(best_fail))
    entry_cmp.to_csv(output / "entry_model_comparison.csv", index=False)
    best_entry = entry_cmp.sort_values(["net_AvgR", "net_PF"], ascending=False).iloc[0]["entry_model"] if not entry_cmp.empty else "BOS_RETEST"

    signal_cache = {
        fdef: dedupe_signals(failure_signals(failures, fdef), market)
        for fdef in WF_FAILURE_DEFS
        if not failure_signals(failures, fdef).empty
    }
    sim_cache = precompute_simulations(signal_cache, market)
    folds, stitched, selections, stab = walk_forward_reversal(
        failures, market, signal_cache=signal_cache, sim_cache=sim_cache
    )
    if not stitched.empty:
        stitched.to_csv(output / "walk_forward_trades.csv", index=False)
    folds.to_csv(output / "walk_forward_folds.csv", index=False)
    selections.to_csv(output / "walk_forward_selections.csv", index=False)
    stab.to_csv(output / "parameter_stability.csv", index=False)

    paths = trade_paths(
        stitched.drop(columns=[c for c in stitched.columns if c.endswith("_sig")], errors="ignore"),
        market,
        stitched,
    ) if not stitched.empty else pd.DataFrame()
    if not paths.empty:
        paths.to_csv(output / "reversal_trade_paths.csv", index=False)
        paths.to_csv(output / "path_geometry.csv", index=False)

    yearly = yearly_results(stitched, market) if not stitched.empty else pd.DataFrame()
    yearly.to_csv(output / "yearly_results.csv", index=False)
    dir_tbl = direction_table(stitched) if not stitched.empty else pd.DataFrame()
    dir_tbl.to_csv(output / "direction_results.csv", index=False)
    disp_dir_tbl = displacement_direction_table(stitched) if not stitched.empty else pd.DataFrame()
    if not disp_dir_tbl.empty:
        disp_dir_tbl.to_csv(output / "direction_results.csv", index=False)

    outlier = outlier_robustness(stitched) if not stitched.empty else pd.DataFrame()
    outlier.to_csv(output / "outlier_robustness.csv", index=False)
    cost = cost_stress(stitched, ARCHITECTURE) if not stitched.empty else pd.DataFrame()
    cost.to_csv(output / "cost_stress.csv", index=False)
    mc = monte_carlo(stitched) if not stitched.empty else {}
    pd.DataFrame([mc]).to_csv(output / "monte_carlo.csv", index=False)

    mono_label, mono_tbl = failure_strength_monotonicity(stitched, strength) if not stitched.empty else ("NO", pd.DataFrame())

    phase31_trades = pd.DataFrame()
    if PHASE31_WF_TRADES.exists():
        phase31_trades = pd.read_csv(PHASE31_WF_TRADES)
        phase31_trades = phase31_trades.loc[phase31_trades.architecture == "MOMENTUM_DISPLACEMENT"].copy()
    interaction = phase31_interaction(phase31_trades, failures, market)
    interaction.to_csv(output / "phase31_interaction.csv", index=False)
    combined = combined_system(phase31_trades, stitched)
    combined.to_csv(output / "combined_system.csv", index=False)

    wf_perf = net_performance(stitched) if not stitched.empty else {"N": 0, "AvgR": 0, "PF": 0, "TotalR": 0, "MaxDD": 0, "ReturnMaxDD": 0, "WinRate": 0}
    daily = daily_distribution(stitched, market) if not stitched.empty else {"mean_signals_day": 0.0}
    passed, checks, classification = success_criteria_phase33(wf_perf, yearly, outlier, cost, mc, mono_label)

    total_disp = len(displacements)
    total_fail_events = len(failures)
    fail_rate = len(continuation.loc[continuation.classification == "FAILURE_REVERSAL"]) / total_disp if total_disp else 0.0
    cont_rate = len(continuation.loc[continuation.classification == "CONTINUATION"]) / total_disp if total_disp else 0.0

    best_sel = selections.iloc[0].to_dict() if not selections.empty else {}
    if not selections.empty:
        mode = selections.mode(numeric_only=False).iloc[0]
        best_fail = mode.get("failure_definition", best_fail)
        best_entry = mode.get("entry_model", best_entry)

    combined_best = combined.sort_values("AvgR", ascending=False).iloc[0] if not combined.empty else None
    best_policy = str(combined_best["policy"]) if combined_best is not None else "INDEPENDENT"

    manifest: Dict[str, Any] = {
        "phase": "Phase 33 — NQ 15M Displacement Failure / Reversal Entry Discovery",
        "architecture": ARCHITECTURE,
        "total_displacements": total_disp,
        "failure_events": total_fail_events,
        "failure_rate": fail_rate,
        "continuation_rate": cont_rate,
        "unresolved_rate": 1.0 - fail_rate - cont_rate,
        "best_failure_definition": str(best_fail),
        "best_entry_model": str(best_entry),
        "walk_forward": wf_perf,
        "trades_day": daily.get("mean_signals_day", 0.0),
        "phase31_benchmark": PHASE31_BENCHMARK,
        "combined_best_policy": best_policy,
        "failure_strength_monotonicity": mono_label,
        "success_checks": checks,
        "checks_passed": passed,
        "classification": classification,
        "ready_for_pine": classification in {"A", "B"},
        "monte_carlo": mc,
        "selections": selections.to_dict(orient="records") if not selections.empty else [],
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    report_lines = [
        "# Displacement Failure / Reversal Report",
        "",
        f"**Classification:** {classification}",
        f"**Ready for Pine:** {'YES' if manifest['ready_for_pine'] else 'NO'}",
        "",
        "## Displacement Population",
        f"- Total displacements: {total_disp:,}",
        f"- Failure events (all definitions): {total_fail_events:,}",
        f"- Failure rate (primary classification): {fail_rate:.1%}",
        f"- Continuation rate: {cont_rate:.1%}",
        "",
        "## Best Walk-Forward Selection",
        f"- Failure definition: {best_fail}",
        f"- Entry model: {best_entry}",
        "",
        "## Stitched Walk-Forward (Phase 33 Reversal)",
        f"- N: {wf_perf.get('N', 0)}",
        f"- Trades/day: {daily.get('mean_signals_day', 0):.2f}",
        f"- Net AvgR: {wf_perf.get('AvgR', 0):.3f}",
        f"- Net PF: {wf_perf.get('PF', 0):.2f}",
        f"- MaxDD: {wf_perf.get('MaxDD', 0):.1f}R",
        "",
        "## Phase 31 Benchmark",
        f"- N: {PHASE31_BENCHMARK['N']}",
        f"- Net AvgR: {PHASE31_BENCHMARK['AvgR']}",
        f"- Net PF: {PHASE31_BENCHMARK['PF']}",
        "",
        "## Combined System",
        combined.to_string(index=False) if not combined.empty else "_No combined results_",
        "",
        f"**Most important finding:** Failed displacement {'shows' if wf_perf.get('AvgR', 0) > 0 else 'does not show'} independent walk-forward reversal edge.",
    ]
    (output / "DISPLACEMENT_FAILURE_REVERSAL_REPORT.md").write_text("\n".join(report_lines) + "\n")

    tables = {
        "failure_events": failures.head(5000),
        "failure_comparison": fail_cmp,
        "entry_comparison": entry_cmp,
        "wf_trades": stitched,
        "wf_selections": selections,
        "yearly": yearly,
        "direction": disp_dir_tbl,
        "path_geometry": paths,
        "continuation": continuation,
        "interaction": interaction,
        "combined": combined,
        "cost": cost,
        "outlier": outlier,
        "monte_carlo": pd.DataFrame([mc]),
    }
    _write_excel(output / "DISPLACEMENT_FAILURE_REVERSAL.xlsx", tables)

    return manifest


if __name__ == "__main__":
    run_phase33()
