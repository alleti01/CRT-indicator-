# Phase62 — Causal Opportunity Trader & Management Design

Builds on Phase61 early-signal audit. Tests invalidation, profit protection, and candidate trader architectures on 87,798 causal opportunities.

## Run

```bash
python3 phase62/tools/run_phase62_audit.py
```

## Artifacts

- `reports/PHASE62_CAUSAL_OPPORTUNITY_TRADER.md`
- `reports/phase62_audit.json`
- `diagnostics/visual_review/best_candidate_sample.csv`

## Key finding

Management (wider/hybrid invalidation) matters more than additional filters. Profit protection rules tested (BE, partial, MFE giveback) **hurt** vs hybrid stop alone. Best candidate: **Trader A** — early entry, hybrid invalidation (1.75 ATR cap), fixed 2.5R, no protection.
