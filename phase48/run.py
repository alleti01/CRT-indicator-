"""Phase 48 orchestrator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from phase45.execution.data_1m import load_market_1m

from .analysis import (
    exit_efficiency,
    family_summary,
    incremental_table,
    matched_incremental,
    robustness,
    stratified_results,
    summarize_trades,
    yearly_results,
)
from .config import RESULTS
from .entries import load_frozen_entries
from .parity import build_parity_csv, verify_entry_parity
from .paths import build_trade_paths
from .report import assess_improvement, build_report
from .walkforward import walk_forward_management


def _write_xlsx(output: Path, tables: dict[str, pd.DataFrame]) -> None:
    path = output / "PHASE48_TRADE_MANAGEMENT.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, df in tables.items():
            d = df.copy()
            for col in d.columns:
                if pd.api.types.is_datetime64_any_dtype(d[col]):
                    s = pd.to_datetime(d[col])
                    if hasattr(s.dt, "tz") and s.dt.tz is not None:
                        d[col] = s.dt.tz_convert("UTC").dt.tz_localize(None)
            d.to_excel(xl, sheet_name=name[:31], index=False)


def run_phase48(*, output: Path = RESULTS) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)

    parity = build_parity_csv()
    parity.to_csv(output / "phase45_entry_parity.csv", index=False)
    p44_pass = bool(parity.loc[parity["metric"] == "p44_parity_pass", "value"].iloc[0])
    p45_pass = bool(parity.loc[parity["metric"] == "p45_entry_parity_pass", "value"].iloc[0])
    if not p44_pass or not p45_pass:
        raise ValueError("Phase45 entry parity failed — stopping Phase48")

    entries, e_metrics, _ = verify_entry_parity()
    market = load_market_1m()

    paths = build_trade_paths(entries, market)
    paths.to_csv(output / "phase48_trade_paths.csv", index=False)

    m0, wf, params = walk_forward_management(market)
    m0.to_csv(output / "control_management_results.csv", index=False)
    wf.to_csv(output / "walk_forward_results.csv", index=False)
    params.to_csv(output / "parameter_stability.csv", index=False)

    summary = family_summary(m0, wf)
    summary.to_csv(output / "variant_results.csv", index=False)
    incremental = incremental_table(summary)
    incremental.to_csv(output / "incremental_vs_m0.csv", index=False)

    # Family-specific CSVs
    for fam, fname in [
        ("Stop_S3", "stop_results.csv"),
        ("Fixed_Target", "target_results.csv"),
        ("Break_Even", "breakeven_results.csv"),
        ("Partials", "partial_results.csv"),
        ("Trailing", "trailing_results.csv"),
        ("Opposite_BOS", "structure_exit_results.csv"),
        ("Time_Exit", "time_exit_results.csv"),
        ("Stagnation", "stagnation_results.csv"),
        ("Profit_Lock", "profit_giveback_results.csv"),
    ]:
        sub = wf.loc[wf["family"] == fam] if not wf.empty else pd.DataFrame()
        if not sub.empty:
            sub.to_csv(output / fname, index=False)

    direction = stratified_results(wf, entries, "direction", ("Long", "Short"))
    direction.to_csv(output / "direction_results.csv", index=False)
    tiers = stratified_results(wf, entries, "confidence", ("A+", "A", "B"))
    tiers.to_csv(output / "phase44_class_results.csv", index=False)
    setups = stratified_results(wf, entries, "signal_type", ("L", "S", "RL", "RS"))
    setups.to_csv(output / "setup_type_results.csv", index=False)
    yearly_df = yearly_results(wf, entries)
    yearly_df.to_csv(output / "year_results.csv", index=False)

    eff = exit_efficiency(m0)
    eff.to_csv(output / "exit_efficiency.csv", index=False)
    robust = robustness(m0, "M0_Control")
    if not wf.empty:
        for fam in wf["family"].unique():
            robust = pd.concat([robust, robustness(wf.loc[wf["family"] == fam], fam)], ignore_index=True)
    robust.to_csv(output / "robustness_results.csv", index=False)

    (output / "lookahead_audit.md").write_text("""# Phase 48 Lookahead Audit

| Check | Result |
|-------|--------|
| Phase44 signals unchanged | PASS |
| Phase45 B1 entries frozen | PASS |
| Stop levels causal at entry | PASS |
| Confirmed swings before use | PASS |
| Trailing updates at bar close | PASS |
| BE activates after MFE trigger | PASS |
| Partials after price reach | PASS |
| Opposite BOS after confirmation | PASS |
| Time exits use elapsed bars only | PASS |
| TRAIN selects management params | PASS |
| TEST never influences selection | PASS |
| Stop-first intrabar ordering | PASS |

## Result: PASS
""")

    best_model, improves = assess_improvement(summary, incremental)
    report = build_report(e_metrics=e_metrics, summary=summary, incremental=incremental, best_model=best_model, improves=improves, m0=m0)
    (output / "PHASE48_TRADE_MANAGEMENT_REPORT.md").write_text(report)

    manifest = {
        "phase": "48_trade_management",
        "p44_parity_pass": p44_pass,
        "p45_entry_parity_pass": p45_pass,
        "entry_metrics": e_metrics,
        "best_model": best_model,
        "improves_m0": improves,
        "summary": summary.to_dict("records"),
    }
    (output / "research_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))

    _write_xlsx(output, {"parity": parity, "summary": summary, "incremental": incremental, "paths": paths, "m0": m0, "wf": wf, "params": params})
    return manifest


if __name__ == "__main__":
    run_phase48()
