# Phase 19 predeclared walk-forward plan

This plan was frozen after the exact baseline-reproduction gate passed and
before any Phase 19 hypothesis or held-out fold result was calculated.

## Scope

- Base model: the original frozen Phase 14/16 BOS model only.
- Available history: 2021-01-01 through 2026-06-26, all treated as development
  research in Phase 19.
- No Phase 17 C1/C2 rule is eligible; both were rejected in Phase 18.
- Features must be known at the BOS entry-bar close. Outcome-derived and
  future-window features are prohibited.

## Expanding chronological folds

1. Train 2021; evaluate 2022.
2. Train 2021-2022; evaluate 2023.
3. Train 2021-2023; evaluate 2024.
4. Train 2021-2024; evaluate 2025.
5. Train 2021-2025; evaluate 2026-01-01 through 2026-06-26.

Within each fold, the training rows alone select at most one one-condition BOS
rule from the registered categorical hypotheses. Ranking is deterministic:
realistic-cost Total R, then ideal-cost Avg R, then N. The selected condition is
then applied unchanged to the immediately following evaluation period. If no
training condition is eligible, the fold records `NO_SELECTION` and no fallback
condition is invented.

## Training eligibility

- one condition only; no interaction may be selected by the walk-forward rule;
- N at least 200 in that fold's training sample;
- ideal Avg R greater than zero and PF greater than 1.05;
- positive Total R after the predeclared realistic cost of $14.50 per trade;
- one-sided mean test p below 0.05 in training;
- positive ideal Total R after removing the five largest winning trades.

## Final Phase 19 candidate screen

A globally registered one-condition or two-condition rule can become P19-C1,
P19-C2, or P19-C3 only if all of the following hold:

- combined N at least 500;
- ideal Avg R positive and PF at least 1.10;
- realistic-cost Total R positive;
- Benjamini-Hochberg FDR q at most 0.10 across all adequately sampled registered
  hypotheses;
- positive ideal Total R in at least four of the six calendar-year buckets
  (2026 is explicitly partial);
- positive ideal Total R after removing the top 1% of winning outcomes;
- no single year supplies more than 60% of all positive-year gross Total R;
- the exact condition is positive in at least four of the five evaluation folds
  and realistic-cost positive in at least three of them;
- a nearby categorical or threshold sensitivity check shows a plateau rather
  than one isolated winning cell.

Complexity is penalized lexicographically: one-condition rules rank ahead of
two-condition rules unless the interaction improves realistic-cost Total R by
at least 25% and satisfies every other requirement. At most three nonredundant
candidates may be frozen. Zero candidates is an acceptable result.

## Cost assumptions

NQ is modeled at $20 per index point and $5 per tick. Costs are converted to R
trade by trade using each trade's fixed stop distance:

- Zero: $0.00 per round trip.
- Optimistic: one-half tick per side plus $4.50 fees = $9.50.
- Realistic: one tick per side plus $4.50 fees = $14.50.
- Conservative: two ticks per side plus $8.00 fees = $28.00.
- Severe: three ticks per side plus $10.00 fees = $40.00.

This file is the ex-ante record. It must not be edited in response to evaluation
results.
