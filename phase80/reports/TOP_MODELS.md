# Phase80 Top Models (train-ranked; validation failed)

## Best single (train)
- **Rule:** `F_M5_DIRECTION_ALIGN` — 5m developing state aligns with signal direction
- **N train:** 5,921 (27.3% retention)
- **ΔAvgR train:** +0.0266
- **Role:** CONTEXT (uses existing signal direction, not new direction)
- **Validation:** Did not meet N≥200 survivor gate on unchanged rule

## Best pair (train)
- **Rule:** `F_M5_DIRECTION_ALIGN AND F_MARKET_REVERSAL`
- **ΔAvgR train:** +0.1728
- **Validation ΔAvgR:** insufficient sample / failed

## Best triple (train — overfit)
- **Rule:** `F_REACTION_SCORE AND F_ALIGNED_ACTIVE AND F_MARKET_REVERSAL`
- **N train:** 3 trades only — **INSUFFICIENT_SAMPLE**
- **ΔAvgR train:** +1.33 (not meaningful)

## Role-gated model
- **Rule:** (good_location OR location_score) AND (reaction_score OR reversal_strong) AND no HTF contra AND false_rev low AND no pullback
- See `ALL_COMBINATIONS.csv` row `ROLE_GATED_V1`

## Random-direction note
Train-topping triples with tiny N show high `random_control_result` — likely activity/timing selection, not robust directional edge.

## Verdict implication
No finalist survived validation with adequate N. **Do not modify Phase72A or production.**
