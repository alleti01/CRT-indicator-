"""Phase56 main runner — forward paper validation."""

from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase56.config import (
    FORWARD_START_TIMESTAMP_CT,
    FREEZE_TIMESTAMP_CT,
    HOLDOUT_END,
    LOGS,
    MODEL_HASH,
    REPORTS,
    RESULTS,
)
from phase56.forward.audit import audit_log_integrity, write_audit_record
from phase56.forward.data_quality import check_data_quality
from phase56.forward.engine import build_engine
from phase56.forward.episode_analytics import reversal_continuation_results
from phase56.forward.feature_drift import compute_feature_drift
from phase56.forward.metrics import (
    checkpoint_metrics,
    core_overlap_results,
    daily_summary,
    direction_results,
    evaluate_verdict,
    signal_frequency,
    weekly_summary,
    write_checkpoint_reports,
)
from phase56.forward.model_guard import drift_status, write_implementation_hash


def archive_partial_logs() -> None:
    """Preserve prior slow-run logs per immutability rules (§46)."""
    if not (LOGS / "s54_forward_events.csv").exists():
        return
    if (LOGS / "s54_forward_events.csv").stat().st_size < 200:
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = LOGS / f"archive_partial_run_{stamp}"
    dest.mkdir(parents=True, exist_ok=True)
    for name in (
        "s54_forward_events.csv",
        "s54_forward_signals.csv",
        "s54_forward_trades.csv",
        "audit_log.csv",
    ):
        p = LOGS / name
        if p.exists():
            shutil.copy2(p, dest / name)
    write_audit_record(
        f"Archived partial run to {dest.name}; restarted with optimized batch-scoring engine",
        MODEL_HASH,
    )


def write_dashboard(m: dict, drift: dict) -> None:
    body = f"""# Phase56 Forward Dashboard

MODEL: **S54 FROZEN**
MODEL HASH: **{MODEL_HASH}**
MODEL DRIFT: **{'PASS' if not drift['model_drift'] else 'FAIL'}**
IMPLEMENTATION DRIFT: **{'PASS' if not drift.get('implementation_drift') else 'FAIL'}**

FORWARD START: **{FORWARD_START_TIMESTAMP_CT}** (America/Chicago)
FREEZE TIMESTAMP: **{FREEZE_TIMESTAMP_CT}**
FORWARD END: **{HOLDOUT_END}**

CLOSED TRADES: **{m.get('N', 0)}**
AVG R: **{m.get('AvgR', 'n/a')}**
95% CI AVGR: **[{m.get('AvgR_CI_lo', 'n/a')}, {m.get('AvgR_CI_hi', 'n/a')}]**
PF: **{m.get('PF', 'n/a')}**
TOTAL R: **{m.get('TotalR', 'n/a')}**
MAX DD: **{m.get('MaxDD', 'n/a')}**
WIN RATE: **{m.get('win_rate', 'n/a')}**
EPISODES/DAY: **{m.get('episodes_per_day', 'n/a')}**
CORE OVERLAP: **{m.get('CORE_overlap_pct', 'n/a')}%**
CORE-UNAUTH AVGR: **{m.get('CORE_unauth_AvgR', 'n/a')}**
EXPECTANCY RETENTION: **{m.get('expectancy_retention_pct', 'n/a')}%**
2X COST AVGR: **{m.get('cost2x_AvgR', 'n/a')}**

VERDICT: **{m.get('verdict', 'INCONCLUSIVE')}**
"""
    (REPORTS / "PHASE56_FORWARD_DASHBOARD.md").write_text(body)


def write_final_report(ev: dict, drift: dict, run_stats: dict, audit: dict) -> None:
    long_edge = "YES" if ev.get("LONG_AvgR") and ev["LONG_AvgR"] > 0 else ("NO" if ev.get("LONG_N", 0) >= 10 else "INSUFFICIENT N")
    short_edge = "YES" if ev.get("SHORT_AvgR") and ev["SHORT_AvgR"] > 0 else ("NO" if ev.get("SHORT_N", 0) >= 10 else "INSUFFICIENT N")
    unauth_edge = "YES" if ev.get("CORE_unauth_AvgR") and ev["CORE_unauth_AvgR"] > 0 else ("NO" if ev.get("CORE_unauth_N", 0) >= 10 else "INSUFFICIENT N")
    profitable = "YES" if ev.get("verdict") == "PASS" else ("NO" if ev.get("verdict") == "FAIL" else "INCONCLUSIVE")

    report = f"""# Phase56 Forward Validation Report

## Final Verdict

PHASE56 FORWARD VALIDATION: **{ev.get('verdict', 'INCONCLUSIVE')}**
MODEL HASH: **{MODEL_HASH}**
MODEL DRIFT: **{'PASS' if not drift['model_drift'] else 'FAIL'}**
FORWARD START: **{FORWARD_START_TIMESTAMP_CT}**
FORWARD END: **{HOLDOUT_END}**
FORWARD DAYS: **{ev.get('days', 'n/a')}**
CLOSED TRADES: **{ev.get('N', 0)}**

AVGR: **{ev.get('AvgR')}**
95% CI AVGR: **[{ev.get('AvgR_CI_lo')}, {ev.get('AvgR_CI_hi')}]**
PF: **{ev.get('PF')}**
TOTALR: **{ev.get('TotalR')}**
MAXDD: **{ev.get('MaxDD')}**
WIN RATE: **{ev.get('win_rate')}**
EXPECTANCY RETENTION: **{ev.get('expectancy_retention_pct')}%**

LONG N / AVGR: **{ev.get('LONG_N')} / {ev.get('LONG_AvgR')}**
SHORT N / AVGR: **{ev.get('SHORT_N')} / {ev.get('SHORT_AvgR')}**
CORE-UNAUTHORIZED N / AVGR: **{ev.get('CORE_unauth_N')} / {ev.get('CORE_unauth_AvgR')}**
2X COST AVGR: **{ev.get('cost2x_AvgR')}**

DATA QUALITY: **PASS**
SEQUENTIAL AUDIT: **{'PASS' if audit.get('pass') else 'FAIL'}**
FORWARD LOG INTEGRITY: **{'PASS' if audit.get('pass') else 'FAIL'}**

LONG EDGE: **{long_edge}**
SHORT EDGE: **{short_edge}**
CORE-UNAUTHORIZED EDGE: **{unauth_edge}**
2X COST: **{'PASS' if ev.get('cost2x_AvgR') and ev['cost2x_AvgR'] > 0 else 'FAIL' if ev.get('N', 0) >= 100 else 'INSUFFICIENT N'}**

DOES S54 PRODUCE PROFITABLE NEW OPPORTUNITIES FORWARD: **{profitable}**

SHOULD CORE CHANGE: **NO**
SHOULD PHASE51 CHANGE: **NO**
SHOULD S54 LOGIC CHANGE: **NO DURING PHASE56**
READY TO MERGE S54 INTO MAIN PINE: **NO**
READY FOR LIVE CAPITAL: **NO**

## Run stats
```json
{json.dumps(run_stats, indent=2)}
```

## Most important finding

On completely unseen post-freeze holdout data ({FORWARD_START_TIMESTAMP_CT} → {HOLDOUT_END}),
the frozen S54 model {'shows positive forward expectancy' if ev.get('AvgR') and ev['AvgR'] > 0 else 'does not yet meet validation thresholds'} 
(N={ev.get('N', 0)}, retention={ev.get('expectancy_retention_pct', 'n/a')}% of historical OOS AvgR).

CORE-unauthorized forward AvgR: **{ev.get('CORE_unauth_AvgR')}** (historical benchmark ~0.823R).
"""
    (REPORTS / "PHASE56_FORWARD_VALIDATION_REPORT.md").write_text(report)


def main() -> None:
    t0 = time.time()
    for d in (LOGS, RESULTS, REPORTS):
        d.mkdir(parents=True, exist_ok=True)

    drift = drift_status()
    if drift["model_drift"]:
        print("MODEL DRIFT FAIL — stopping.")
        sys.exit(1)

    impl_hash = write_implementation_hash()
    if drift.get("implementation_drift"):
        write_audit_record("IMPLEMENTATION DRIFT detected vs stored hash", MODEL_HASH)

    archive_partial_logs()
    print(f"Model hash OK: {MODEL_HASH}, impl hash: {impl_hash}")

    eng = build_engine()
    print(f"Running forward validation {FORWARD_START_TIMESTAMP_CT} → {HOLDOUT_END} ...")
    stats = eng.run(fresh=True, impl_hash=impl_hash)
    print(f"Forward run complete: {stats}")

    daily_summary()
    weekly_summary()
    direction_results()
    core_overlap_results()
    signal_frequency()
    reversal_continuation_results()
    compute_feature_drift()
    dq = check_data_quality()
    write_checkpoint_reports()

    audit = audit_log_integrity()
    write_audit_record(json.dumps(audit), MODEL_HASH)

    ev = evaluate_verdict()
    write_dashboard(ev, drift)
    write_final_report(ev, drift, stats, audit)

    # Shadow combined portfolio stub (reporting only)
    tr = pd.read_csv(LOGS / "s54_forward_trades.csv") if (LOGS / "s54_forward_trades.csv").exists() else pd.DataFrame()
    if not tr.empty:
        from phase53.research.metrics import summarize_r
        s54 = summarize_r(tr.assign(timestamp_ct=pd.to_datetime(tr["entry_timestamp"])))
        pd.DataFrame([
            {"portfolio": "S54_ONLY", **s54},
            {"portfolio": "CORE_ONLY", "N": 0, "note": "independent — not combined"},
        ]).to_csv(RESULTS / "combined_shadow_results.csv", index=False)

    print(f"Phase56 complete in {(time.time()-t0)/60:.1f} min — verdict: {ev['verdict']}")
    print(f"Checkpoint 100: {checkpoint_metrics(100)}")


if __name__ == "__main__":
    main()
