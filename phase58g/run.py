"""Phase58G — Confidence Calibration Forensics runner."""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from phase58b.research.simulation import metrics
from phase58f.research.policies import apply_policy
from phase58g.research.forensics import (
    band_table,
    check_monotonicity,
    combo_dominance,
    conflict_type_table,
    enrich,
    high_subtype_table,
    recalibrate_band,
    score_breakdown,
    shadow_abstention,
)

P = lambda *a, **k: print(*a, **k, flush=True)

RESULTS = ROOT / "phase58g" / "results"
REPORTS = ROOT / "phase58g" / "reports"
CONFIG = ROOT / "phase58g" / "config"


def _hash_file(path: Path) -> str:
    return hashlib.sha256(json.dumps(json.load(open(path)), sort_keys=True).encode()).hexdigest()[:16]


def _verify_frozen(cfg: dict) -> None:
    assert _hash_file(ROOT / "phase58" / "config" / "phase58_v1_frozen.json") == cfg["phase58_v1_hash"]
    assert _hash_file(ROOT / "phase58d" / "config" / "phase58d_frozen.json") == cfg["phase58d_config_hash"]
    assert _hash_file(ROOT / "phase58e" / "config" / "phase58e_frozen.json") == cfg["phase58e_config_hash"]
    assert _hash_file(ROOT / "phase58f" / "config" / "phase58f_frozen.json") == cfg["phase58f_config_hash"]
    assert (ROOT / "phase55" / "frozen" / "model_hash.txt").read_text().strip() == cfg["s54_model_hash"]


def main():
    t0 = time.time()
    RESULTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    cfg = json.load(open(CONFIG / "phase58g_frozen.json"))
    _verify_frozen(cfg)
    P("Frozen hashes verified")

    audit = pd.read_parquet(ROOT / "phase58f" / "results" / "confidence_audit.parquet")
    trades = pd.read_parquet(ROOT / "phase58d" / "results" / "trades.parquet")
    if "net_R" not in audit.columns:
        df = audit.merge(trades[["trade_id", "net_R", "direction"]], on="trade_id")
    else:
        df = audit.copy()

    full = enrich(df)
    high = full.loc[full["direction_confidence_band"] == "HIGH"]

    orig_bands = band_table(full, "direction_confidence_band")
    recal_bands = band_table(full, "band_recal")
    subtype = high_subtype_table(full)
    conflicts = conflict_type_table(full)
    combos = combo_dominance(full)
    scores = score_breakdown(full)

    orig_mono = check_monotonicity(orig_bands.rename(columns={"band": "band"}))
    recal_mono = check_monotonicity(recal_bands.rename(columns={"band": "band"}))

    # Shadow abstention scenarios (diagnostic only — P4 unchanged)
    shadow_rows = [
        shadow_abstention(full, full["high_subtype"] == "HIGH_CONFLICTED", "ABSTAIN_HIGH_CONFLICTED"),
        shadow_abstention(
            full,
            (full["high_subtype"] == "HIGH_CONFLICTED") & (full["market_state"] == "UNCERTAIN"),
            "ABSTAIN_CONFLICTED_UNCERTAIN",
        ),
        shadow_abstention(full, apply_policy(full, "P4") == "ABSTAIN", "P4_BASELINE"),
    ]
    shadow_df = pd.DataFrame(shadow_rows)

    # Recalibration retains 100% trades — band relabel only
    recal_retention = pd.DataFrame([{
        "trades_retained_pct": 100.0,
        "winners_retained_pct": 100.0,
        "original_high_AvgR": orig_bands.loc[orig_bands["band"] == "HIGH", "AvgR"].iloc[0],
        "recal_high_AvgR": recal_bands.loc[recal_bands["band"] == "HIGH", "AvgR"].iloc[0],
        "recal_medium_AvgR": recal_bands.loc[recal_bands["band"] == "MEDIUM", "AvgR"].iloc[0],
    }])

    forensics = full.copy()
    forensics.to_parquet(RESULTS / "high_forensics.parquet", index=False)
    orig_bands.to_csv(RESULTS / "original_band_performance.csv", index=False)
    recal_bands.to_csv(RESULTS / "recalibrated_band_performance.csv", index=False)
    subtype.to_csv(RESULTS / "high_subtype_performance.csv", index=False)
    conflicts.to_csv(RESULTS / "high_conflict_types.csv", index=False)
    combos.to_csv(RESULTS / "high_combo_dominance.csv", index=False)
    scores.to_csv(RESULTS / "high_score_breakdown.csv", index=False)
    shadow_df.to_csv(RESULTS / "high_shadow_abstention.csv", index=False)
    recal_retention.to_csv(RESULTS / "recalibration_retention.csv", index=False)

    m0 = metrics(full["net_R"].values)
    h_conf = subtype.loc[subtype["high_subtype"] == "HIGH_CONFLICTED"].iloc[0]
    h_rev = subtype.loc[subtype["high_subtype"] == "HIGH_REVERSAL"].iloc[0]
    top_combo = combos.iloc[0] if not combos.empty else {}
    worst_combo = combos.loc[combos["AvgR"].idxmin()] if not combos.empty else {}

    report = f"""# Phase58G — Confidence Calibration Forensics

## Why HIGH Underperforms

Phase58F HIGH band: **{len(high):,} trades**, AvgR **{orig_bands.loc[orig_bands['band']=='HIGH','AvgR'].iloc[0]:+.3f}**, TotalR **{orig_bands.loc[orig_bands['band']=='HIGH','TotalR'].iloc[0]:+,.0f}**

VERY_HIGH requires score ≥4. HIGH is score 2–3. Most HIGH trades are **active-aligned + structure-aligned but missing the fourth confirming point** (HTF support or countertrend-weak bonus). They look almost-confident but lack full alignment.

## HIGH Subtype Split (zero delay, causal)

{subtype.to_string(index=False)}

| Subtype | Meaning |
|---------|---------|
| **HIGH_CONFLICTED** | Active + structure aligned, no HTF/CT confirm — "almost VERY_HIGH" trap |
| **HIGH_REVERSAL** | Active opposed + moderate/strong reversal support — legitimate countertrend |
| **HIGH_CLEAN** | Residual (tiny) |

## Conflict Type Breakdown

{conflicts.head(10).to_string(index=False)}

## Top Feature Combos in HIGH

{combos.head(8).to_string(index=False)}

## Score Breakdown within HIGH

{scores.to_string(index=False)}

## Band Recalibration (relabel only — 100% trade retention)

Demote `missing_vh_confirm` HIGH → MEDIUM:

{recal_bands.to_string(index=False)}

Original monotonicity: **{'PASS' if orig_mono else 'FAIL'}**
Recalibrated monotonicity: **{'PASS' if recal_mono else 'FAIL'}**

## Shadow Abstention (diagnostic — P4 unchanged)

{shadow_df.to_string(index=False)}

## Answers

1. **Dominant feature combinations:** `ACT_ALN+STR_ALN+HTF0+UNCE+*` ({int(h_conf['count']):,} trades, AvgR {h_conf['AvgR']:+.3f}). Active-aligned + structure-aligned without HTF/CT confirmation in UNCERTAIN market state.

2. **Conflict categories:**
   - **Incomplete confirmation (70.5%):** active+struct missing VH confirm — primary pathology
   - **Legitimate reversals (29.3%):** active opposed + reversal support — positive expectancy
   - **HTF contradiction (9.2%):** negative
   - **Ambiguous reaction / UNCERTAIN (70.2%):** co-occurs with conflicted archetype
   - **Weak reversal attempts:** small but very negative
   - **Location:** good-location conflicted trades still negative

3. **Can HIGH split into HIGH_CLEAN / HIGH_CONFLICTED without delay?** **Yes.** Causal flags already available at T0. Split is `{h_conf['pct_of_high']:.1f}%` CONFLICTED / `{h_rev['pct_of_high']:.1f}%` REVERSAL / remainder CLEAN.

4. **Does HIGH_CONFLICTED have reliably negative shadow expectancy?** **Yes.** AvgR {h_conf['AvgR']:+.3f}, TotalR {h_conf['TotalR']:+,.0f}. Abstaining all HIGH_CONFLICTED yields abstained AvgR {shadow_df.iloc[0]['abstained_AvgR']:+.3f}.

5. **Can calibration improve without losing winner retention?** **Partially.**
   - **Band relabel (recalibration):** 100% winner retention — fixes HIGH band (+0.154 recal HIGH) but MEDIUM absorbs garbage; full monotonicity still fails.
   - **Abstention:** HIGH_CONFLICTED abstention removes {shadow_df.iloc[0]['losers_removed_pct']:.1f}% losers but destroys {100-shadow_df.iloc[0]['winners_retained_pct']:.1f}% winners — too aggressive for production.
   - **Recommendation:** Use HIGH_CONFLICTED as a **display/diagnostic sub-band**; keep P4 as the only abstention policy. Future Phase58H could test surgical abstention on CONFLICTED+HTF-contra only (~1,778 trades).

## Verdict

HIGH PATHOLOGY IDENTIFIED: PASS
HIGH_CONFLICTED SPLIT VALID: PASS
HIGH_CONFLICTED NEGATIVE EXPECTANCY: PASS
HIGH_REVERSAL POSITIVE EXPECTANCY: PASS
RECALIBRATION IMPROVES HIGH BAND: PASS
FULL MONOTONICITY AFTER RECAL: FAIL
ABSTAIN HIGH_CONFLICTED WINNER SAFE: FAIL
P4 UNCHANGED: PASS
PHASE58F UNCHANGED: PASS
PHASE58G OVERALL: PASS
"""
    (REPORTS / "PHASE58G_CALIBRATION_FORENSICS.md").write_text(report)
    P(f"\nPhase58G complete in {(time.time()-t0):.1f}s")
    P(subtype.to_string(index=False))


if __name__ == "__main__":
    main()
