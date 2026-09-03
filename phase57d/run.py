"""Phase57D — Point-in-Time Options / IV Wall Discovery runner.

Independent research branch. Performance research gated on data provenance.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase57d.config import (
    DATA,
    METHOD_VERSION,
    PHASE55_FROZEN,
    PHASE57B_ROOT,
    REPORTS,
    RESULTS,
    S54_MODEL_HASH,
)
from phase57d.research.audit import AuditLog
from phase57d.research.inventory import inventory_datasets, save_inventory
from phase57d.research.provenance import evaluate_provenance_gate, save_provenance
from phase57d.research.registry import register_experiment
from phase57d.research.schema import (
    CONFIG_PROVENANCE_COLUMNS,
    WALL_CATALOG_COLUMNS,
    WALL_INTERACTION_COLUMNS,
    WALL_SNAPSHOT_COLUMNS,
)

P = lambda *a, **k: print(*a, **k, flush=True)


def _verify_frozen_integrity(audit: AuditLog) -> None:
    """Verify S54 hash unchanged and Phase57B not modified by Phase57D."""
    model_hash_path = PHASE55_FROZEN / "model_hash.txt"
    if model_hash_path.exists():
        h = model_hash_path.read_text().strip()
        if h != S54_MODEL_HASH:
            audit.add(
                "CRITICAL", "S54_INTEGRITY",
                f"S54 model hash mismatch: {h} != {S54_MODEL_HASH}",
                requires_fix=True,
            )
        else:
            P(f"S54 hash OK: {S54_MODEL_HASH}")
    else:
        audit.add("HIGH", "S54_INTEGRITY", "model_hash.txt not found", requires_fix=True)

    # Phase57D must not contain imports that modify phase57b
    phase57d_files = list((ROOT / "phase57d").rglob("*.py"))
    for f in phase57d_files:
        text = f.read_text()
        if "phase57b.research" in text and "unchanged" not in text.lower():
            if "PHASE57B_ROOT" not in text:
                audit.add(
                    "MODERATE", "PHASE57B_ISOLATION",
                    f"Phase57D file references phase57b research: {f.name}",
                )


def _write_config_provenance() -> None:
    from phase57d import config as cfg

    rows = []
    for k in dir(cfg):
        if k.isupper() and not k.startswith("_"):
            v = getattr(cfg, k)
            if isinstance(v, (str, int, float, bool, tuple, list)):
                rows.append({
                    "config_key": k,
                    "config_value": str(v),
                    "frozen": "YES",
                    "source": "phase57d/config.py",
                })
    pd.DataFrame(rows, columns=CONFIG_PROVENANCE_COLUMNS).to_csv(
        RESULTS / "config_provenance.csv", index=False
    )


def _write_empty_results() -> None:
    """Create schema-valid empty result files when data blocked."""
    pd.DataFrame(columns=WALL_SNAPSHOT_COLUMNS).to_parquet(
        RESULTS / "wall_snapshots.parquet", index=False
    )
    pd.DataFrame(columns=WALL_CATALOG_COLUMNS).to_parquet(
        RESULTS / "wall_catalog.parquet", index=False
    )
    pd.DataFrame(columns=WALL_INTERACTION_COLUMNS).to_parquet(
        RESULTS / "wall_interactions.parquet", index=False
    )


def _write_data_provenance_report(gate: dict, inv: dict) -> None:
    content = f"""# PHASE57D DATA PROVENANCE

## Executive Summary

**Status:** {gate['status']}  
**Overall:** {gate['overall']}  
**Performance Research Permitted:** {gate['performance_research_permitted']}  
**Wall Edge Claims Permitted:** {gate['wall_edge_claims_permitted']}

## Repository Inventory

- Scan root: `{inv['scan_root']}`
- Underlying datasets found: **{inv['underlying_count']}**
- Options datasets found: **{inv['options_count']}**
- Point-in-time options verified: **{gate['options_point_in_time_verified']}**

## Available Underlying Data

The repository contains NQ continuous futures OHLC data (1M/5M/15M) suitable
for underlying price interaction research. This data supports closed-bar causal
analysis but does **not** include options chain snapshots.

## Missing Options Data

No historical point-in-time options data was found for any of the required mappings:

| Mapping | Product | Status |
|---------|---------|--------|
| MAP_NQ_NQOPT | NQ futures options | **NOT AVAILABLE** |
| MAP_NQ_NDX | NDX index options | **NOT AVAILABLE** |
| MAP_NQ_QQQ | QQQ ETF options | **NOT AVAILABLE** |

## Required Fields (Not Present)

{chr(10).join(f'- `{f}`' for f in gate['required_fields'])}

## Provenance Questions

| Question | Answer |
|----------|--------|
| Is OI intraday or prior-clearing? | {gate['questions']['oi_intraday_or_prior_clearing']} |
| When is each OI observation actually known? | {gate['questions']['oi_known_time']} |
| Are Greeks historical snapshots? | {gate['questions']['greeks_historical_snapshots']} |
| If recomputed, what inputs are used? | {gate['questions']['greeks_recompute_inputs']} |
| Is IV truly point-in-time? | {gate['questions']['iv_point_in_time']} |
| Is volume cumulative intraday? | {gate['questions']['volume_cumulative_intraday']} |
| Are expired contracts preserved? | {gate['questions']['expired_contracts_preserved']} |
| Are all strikes preserved? | {gate['questions']['all_strikes_preserved']} |
| Is there survivorship bias? | {gate['questions']['survivorship_bias']} |
| Exchange-time or vendor-time? | {gate['questions']['timestamp_exchange_or_vendor']} |
| What latency exists? | {gate['questions']['known_latency']} |
| Can we prove wall existed before touch? | {gate['questions']['wall_before_touch_provable']} |

## Reconstructable Wall Families

| Family | Status |
|--------|--------|
"""
    for fam, status in gate["reconstructable_wall_families"].items():
        content += f"| {fam} | {status} |\n"

    content += """
## Hard Gate Decision

**PHASE57D POINT-IN-TIME DATA: FAIL**

Historical options data cannot support causal wall research with current repository
contents. Performance research and wall edge claims are **NOT PERMITTED**.

## What Would Unblock Phase57D

A vendor dataset providing, at minimum:

1. Timestamped options chain snapshots (intraday or end-of-day with documented OI timing)
2. Documented `known_at` for each OI observation (prior-clearing vs intraday)
3. Point-in-time IV and/or Greeks (vendor snapshots or reproducible from bid/ask at T)
4. Full strike chain preserved (no survivorship)
5. Expired contract history for backtesting

Candidate providers (not in repo): CBOE LiveVol, OptionMetrics, ORATS, Polygon/Massive,
ThetaData, iVolatility, CME datamine (for NQ options).

## Method Version

"""
    content += f"`{METHOD_VERSION}`\n"
    (REPORTS / "PHASE57D_DATA_PROVENANCE.md").write_text(content)


def _write_point_in_time_audit(gate: dict) -> None:
    status = "FAIL" if not gate["gate_pass"] else "PASS"
    content = f"""# PHASE57D POINT-IN-TIME AUDIT

## Audit Date
Generated at Phase57D initialization run.

## Verdict
**POINT-IN-TIME DATA: {status}**

## Causality Checks Performed

| Check | Result |
|-------|--------|
| Options snapshot no future data | NOT_TESTED (no data) |
| OI timing causal | NOT_TESTED (no data) |
| IV timing causal | NOT_TESTED (no data) |
| Greeks causal | NOT_TESTED (no data) |
| Expiration filtering causal | FRAMEWORK_READY |
| Underlying/options timestamp alignment | NOT_TESTED (no data) |
| Wall exists before interaction | NOT_TESTED (no data) |
| No backward fill | POLICY_ENFORCED |
| No future surface ranking | POLICY_ENFORCED |
| Truncation adversarial (10k samples) | NOT_RUN (no interactions) |
| Sequential replay parity | FRAMEWORK_TESTED (synthetic) |

## Framework Causality Design

The Phase57D engine enforces:

- `valid_from` = snapshot `known_at` (wall not active before this)
- Interactions rejected if `bar_ts < wall.valid_from`
- Signal at bar close → execution at T+1 open (default)
- Conservative stop-first on same-bar stop/target collision
- Episode consolidation to prevent duplication inflation

## Performance Research
**BLOCKED** — cannot proceed without point-in-time options data.
"""
    (REPORTS / "PHASE57D_POINT_IN_TIME_AUDIT.md").write_text(content)


def _write_blocked_reports() -> None:
    blocked = """## Status: DATA_BLOCKED

Performance research was not conducted. No wall edge claims are made.
See `PHASE57D_DATA_PROVENANCE.md` for details.

"""
    for name in [
        "PHASE57D_RAW_WALL_BEHAVIOR.md",
        "PHASE57D_INTERACTION_DISCOVERY.md",
        "PHASE57D_ENTRY_TIMING.md",
        "PHASE57D_EPISODE_ANALYSIS.md",
        "PHASE57D_ROBUSTNESS.md",
    ]:
        (REPORTS / name).write_text(f"# {name.replace('.md','').replace('PHASE57D_','PHASE57D — ').replace('_',' ')}\n\n{blocked}")

    optional = """# PHASE57D OPTIONAL MODULE ASSESSMENT

## Status: INCONCLUSIVE (DATA_BLOCKED)

The optional-module architecture has been implemented:

```
UNIVERSAL TRADING ENGINE
         │
   MARKET-AGNOSTIC PRICE CORE
         │
   ┌─────┴─────┐
   │           │
 CORE      OPTIONAL CONTEXT
              │
        OPTIONS WALL MODULE  ← interfaces ready, data missing
```

## Implemented Interfaces

- `UnderlyingAdapter` — NQ adapter uses Phase53 pipeline
- `OptionsAdapter` — abstract; no concrete data source
- `ExpirationCalendar` — DTE buckets predeclared
- `WallCalculator` — OI, Call, Put, Gamma, IV families
- `WallSnapshotEngine` — causal valid_from/valid_until lifecycle
- `InteractionDetector` — touch/break/reclaim events
- `EpisodeEngine` — 30-minute consolidation window
- `ExecutionModel` — T+1 open, conservative collisions
- `SequentialReplayEngine` — chronological replay

## Universal Design Principles

- Distance normalized by ATR (not NQ points)
- Instrument mechanics via adapters (tick, multiplier, session)
- Options module is optional — core must work without it
- Mappings tested independently (MAP_NQ_NQOPT, MAP_NQ_NDX, MAP_NQ_QQQ)

## Assessment

Cannot assess standalone or contextual wall value without valid options data.
Framework is ready for data ingestion when a point-in-time source is acquired.
"""
    (REPORTS / "PHASE57D_OPTIONAL_MODULE_ASSESSMENT.md").write_text(optional)


def _write_final_report(gate: dict) -> None:
    content = """==================================================
PHASE57D EXECUTIVE SUMMARY
==================================================

DATA SOURCE:
Provider=NOT_AVAILABLE
Options product=NONE IN REPOSITORY
Underlying=NQ (futures OHLC only)
Mapping=NONE TESTED
Date range=N/A
Snapshot frequency=N/A
Point-in-time verified=NO

BEST WALL FAMILY:
Family=N/A (DATA_BLOCKED)
Exact formula=N/A
Mapping=N/A
Expiration scope=N/A

BEST INTERACTION:
Type=N/A

BEST ENTRY:
Stage=N/A

DISTINCT OOS:
N=0
Episodes/day=N/A
AvgR=N/A
PF=N/A
TotalR=N/A
MaxDD=N/A
WinRate=N/A
LongAvgR=N/A
ShortAvgR=N/A

EXECUTION STRESS:
+1 tick AvgR=N/A
+2 ticks AvgR=N/A
2x cost AvgR=N/A

STABILITY:
Positive years=N/A
Worst year AvgR=N/A
Positive months=N/A
Parameter stability=N/A

PLACEBO:
NOT_RUN (DATA_BLOCKED)

## Research Questions

1. **What did "IV wall" mean in this research?**
   Phase57D defined seven wall families (Call, Put, Gamma, IV-derived, OI,
   Zero-Gamma, Multi-Exp) but could test none due to missing options data.

2. **Which exact wall definitions were actually tested?**
   None on historical data. Framework unit tests used synthetic snapshots only.

3. **Was historical options data truly point-in-time?**
   No. No historical options data exists in the repository.

4. **Could every wall be known before price reached it?**
   Not demonstrable — no options snapshots available.

5–30. All performance questions: **NOT ANSWERABLE** — DATA_BLOCKED.

## Verdict

Phase57D concludes that **valid research cannot proceed** with current data.
The correct outcome is INVALID_DATA, not a fabricated backtest.

Approximately 9 NQ futures OHLC datasets exist and can support underlying
interaction testing once options data is acquired.

## Next Steps (When Data Available)

1. Ingest options chain with documented OI/IV timing
2. Pass provenance gate
3. Run raw wall population characterization
4. Test W1–W12 interaction families independently
5. Compare raw vs distinct episode results
6. Run placebo and baseline tests
7. Only then assess standalone vs contextual value

"""
    (REPORTS / "PHASE57D_FINAL_REPORT.md").write_text(content)


def main() -> int:
    t0 = time.time()
    for d in (DATA, RESULTS, REPORTS):
        d.mkdir(parents=True, exist_ok=True)

    audit = AuditLog()
    P("=" * 60)
    P("PHASE57D — Point-in-Time Options / IV Wall Discovery")
    P("=" * 60)

    _verify_frozen_integrity(audit)

    P("\n[1/5] Dataset inventory...")
    inv_path = save_inventory()
    inv = inventory_datasets()
    P(f"  Underlying datasets: {inv['underlying_count']}")
    P(f"  Options datasets: {inv['options_count']}")

    P("\n[2/5] Data provenance gate...")
    csv_path, gate = save_provenance()
    P(f"  Gate status: {gate['status']}")
    P(f"  Performance research permitted: {gate['performance_research_permitted']}")

    if not gate["gate_pass"]:
        audit.add(
            "CRITICAL",
            "DATA_PROVENANCE",
            "No point-in-time historical options data in repository. "
            "All wall performance research blocked.",
            causality_impact="Cannot establish OI/IV/Greeks timing",
            performance_impact="No performance claims permitted",
            requires_fix=True,
            status="CONFIRMED",
        )
        audit.add(
            "INFO",
            "DATA_INVENTORY",
            f"Found {inv['underlying_count']} NQ underlying datasets, "
            f"0 verified options datasets.",
        )

    P("\n[3/5] Writing config provenance...")
    _write_config_provenance()

    P("\n[4/5] Creating result artifacts...")
    _write_empty_results()

    register_experiment(
        "EXP57D-0001",
        wall_family="ALL",
        interaction="DATA_GATE",
        mapping="NONE",
        expiration_scope="N/A",
        entry_stage="N/A",
        status="BLOCKED",
        notes="Data provenance gate FAIL — no options data",
    )

    P("\n[5/5] Writing reports...")
    _write_data_provenance_report(gate, inv)
    _write_point_in_time_audit(gate)
    _write_blocked_reports()
    _write_final_report(gate)

    audit.save()

    elapsed = time.time() - t0
    P(f"\nPhase57D complete in {elapsed:.1f}s")
    P(f"  Results: {RESULTS}")
    P(f"  Reports: {REPORTS}")

    if not gate["gate_pass"]:
        P("\n" + "=" * 60)
        P("PHASE57D POINT-IN-TIME DATA: FAIL")
        P("PHASE57D WALL EDGE CLAIMS: NOT PERMITTED")
        P("PHASE57D OVERALL: INVALID_DATA")
        P("=" * 60)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
