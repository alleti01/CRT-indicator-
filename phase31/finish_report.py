"""Finish Phase 31 report from existing CSV outputs."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from phase31.config import PHASE30_EXEC, RESULTS, SHORTLIST_EXECUTION_GRID
from phase31.signals import ARCHITECTURES
from phase31.data import load_market_15m
from phase31.metrics import (
    classify,
    cost_stress,
    daily_distribution,
    frequency_frontier,
    monte_carlo,
    net_performance,
    outlier_robustness,
    performance,
    success_criteria,
    yearly_results,
)


def _direction_table(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for direction in ("Long", "Short"):
        sub = trades.loc[trades["direction"] == direction] if not trades.empty else pd.DataFrame()
        rows.append({"direction": direction, **performance(sub, col="net_R")})
    return pd.DataFrame(rows)


def _write_excel(output: Path, tables: dict) -> None:
    try:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for name, df in tables.items():
                sheet = name[:31]
                out = df.copy() if not df.empty else pd.DataFrame({"note": ["empty"]})
                for col in out.select_dtypes(include=["datetimetz"]).columns:
                    out[col] = out[col].dt.tz_localize(None)
                out.to_excel(writer, sheet_name=sheet, index=False)
    except (ImportError, ValueError):
        pass


def finish_report(output: Path = RESULTS) -> None:
    market = load_market_15m()
    wf = pd.read_csv(output / "walk_forward_trades.csv", parse_dates=["entry_timestamp"])
    screen = pd.read_csv(output / "candidate_architectures.csv")
    arch_rows = []
    for arch in ARCHITECTURES:
        sub = wf.loc[wf["architecture"] == arch] if not wf.empty else pd.DataFrame()
        perf = net_performance(sub)
        daily = daily_distribution(sub, market)
        arch_rows.append({"architecture": arch, "NetAvgR": perf["AvgR"], "NetPF": perf["PF"], **perf, **daily})
    arch_wf = pd.DataFrame(arch_rows)
    frontier = frequency_frontier(arch_wf)
    frontier.to_csv(output / "frequency_quality_frontier.csv", index=False)

    eligible = arch_wf.loc[(arch_wf["mean_signals_day"] >= 0.5) & (arch_wf["NetAvgR"] > 0)]
    best_arch = (
        eligible.sort_values(["NetAvgR", "NetPF", "ReturnMaxDD"], ascending=False).iloc[0]["architecture"]
        if not eligible.empty
        else arch_wf.sort_values("NetAvgR", ascending=False).iloc[0]["architecture"]
    )
    best = wf.loc[wf["architecture"] == best_arch].copy()
    wf_perf = net_performance(best)
    daily_best = daily_distribution(best, market)
    pd.DataFrame([daily_best]).to_csv(output / "daily_signal_distribution.csv", index=False)
    yearly = yearly_results(best, market)
    yearly.to_csv(output / "yearly_results.csv", index=False)
    direction = _direction_table(best)
    direction.to_csv(output / "direction_results.csv", index=False)
    cost_df = cost_stress(best, best_arch)
    cost_df.to_csv(output / "cost_stress.csv", index=False)
    outlier = outlier_robustness(best)
    outlier.to_csv(output / "outlier_robustness.csv", index=False)
    mc = monte_carlo(best)
    pd.DataFrame([mc]).to_csv(output / "monte_carlo.csv", index=False)
    stab = pd.read_csv(output / "parameter_stability.csv")
    passed, checks = success_criteria(wf_perf, daily_best, yearly, outlier, cost_df, best)
    final_class = classify(passed, wf_perf, daily_best)
    ready = passed >= 14

    sel = pd.read_csv(output / "walk_forward_selections.csv")
    best_sel = sel.loc[sel["architecture"] == best_arch]
    mode_entry = best_sel["entry_model"].mode().iloc[0] if not best_sel.empty else "BOS_RETEST"
    mode_stop = best_sel["stop_atr"].mode().iloc[0] if not best_sel.empty else 0.75
    mode_target = best_sel["target_r"].mode().iloc[0] if not best_sel.empty else 3.0
    mode_hold = best_sel["hold_minutes"].mode().iloc[0] if not best_sel.empty else 60

    baselines = {}
    for label, arch in (
        ("phase30_crt_v2", "CRT_V2_B_LEGACY_EXP6"),
        ("phase28_retest_gated", "RETEST_GATED"),
        ("bos_baseline", "BOS_ONLY"),
    ):
        sub = wf.loc[wf["architecture"] == arch]
        baselines[label] = net_performance(sub)

    lines = [
        "# Phase 31 — NQ 15M Daily-Frequency High-Quality Entry Discovery",
        "",
        f"## Best Architecture: **{best_arch}**",
        f"- Entry model (WF mode): {mode_entry}",
        f"- Stop: {mode_stop} ATR",
        f"- Target: {mode_target}R",
        f"- Max hold: {mode_hold}m",
        "",
        f"Stitched WF N={wf_perf['N']}, trades/day={daily_best['mean_signals_day']:.3f}, Net AvgR={wf_perf['AvgR']:.4f}, PF={wf_perf['PF']:.2f}",
        "",
        f"Success criteria: {passed}/14",
        f"Classification: {final_class}",
        f"READY FOR PINE: {'YES' if ready else 'NO'}",
    ]
    (output / "DAILY_FREQUENCY_ENTRY_REPORT.md").write_text("\n".join(lines))

    manifest = {
        "phase": "Phase 31 — NQ 15M Daily-Frequency High-Quality Entry Discovery",
        "architectures_tested": list(ARCHITECTURES),
        "parameter_combinations_shortlist": len(SHORTLIST_EXECUTION_GRID),
        "best_architecture": best_arch,
        "best_execution": {
            "entry_model": mode_entry,
            "stop_atr": float(mode_stop),
            "target_r": float(mode_target),
            "hold_minutes": int(mode_hold),
            "management": "FIXED",
        },
        "stitched_walk_forward_net": wf_perf,
        "daily_distribution": daily_best,
        "baselines": baselines,
        "success_criteria_passed": passed,
        "checks": {k: v for k, v in checks},
        "final_classification": final_class,
        "ready_for_pine": ready,
        "monte_carlo": mc,
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    _write_excel(
        output / "DAILY_FREQUENCY_ENTRY.xlsx",
        {
            "architectures": screen,
            "wf_trades": wf,
            "frontier": frontier,
            "daily": pd.DataFrame([daily_best]),
            "yearly": yearly,
            "direction": direction,
            "cost": cost_df,
            "outlier": outlier,
            "monte_carlo": pd.DataFrame([mc]),
        },
    )


if __name__ == "__main__":
    finish_report()
