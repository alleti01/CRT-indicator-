# Phase57B — Causal Turn Discovery Report

## Configuration (frozen, normalized for universality)
- Leg: swing=5, min_distance_atr=1.0
- Pullback: min_depth_pct=0.15
- Turn evidence: T1 (close reversal), T2 (body reversal), T3 (wick rejection)
- Trade: 0.75 ATR stop, 2.5R target, 60m hold
- S54 hash: bccf4277f3d44d13 (unchanged)

## Key Results

| View | N | AvgR | PF | WR |
|------|---|------|-----|-----|
| Raw causal turn | 186843 | -0.3664 | 0.626 | 0.285 |
| Next-bar entry | 186843 | -0.3655 | 0.626 | 0.285 |
| 30min episodes | 108250 | -0.3607 | 0.631 | 0.287 |
| One position | 167225 | -0.3669 | 0.626 | 0.285 |
| WF OOS | 105977 | -0.2569 | 0.714 | 0.287 |
| Holdout | 31108 | -0.1537 | 0.814 | 0.288 |
| 2x costs | 186843 | -0.7358 | 0.415 | |
| Placebo | 186843 | -0.3545 | 0.635 | |

## Turn Type Breakdown
- T1: N=109546 AvgR=-0.3676 PF=0.625
- T2: N=53660 AvgR=-0.3878 PF=0.611
- T3: N=23637 AvgR=-0.3117 PF=0.666

## Phase57B Answers

1. **Can Leg1 be identified causally?** YES
2. **Can active pullback be identified causally?** YES
3. **Can we recognize the turn early without future extreme?** NO (T1/T2/T3)
4. **Earliest executable entry?** Turn bar close (0-bar) or next bar (+1)
5. **What improves turn recognition?** See turn type breakdown
6. **ONE structural opportunity?** One turn per leg, 30min episode window
7. **Structural reset?** New leg via swing progression
8. **Edge survives one-entry-per-setup?** NO
9. **Edge survives realistic execution/costs?** NO
10. **Normalized for universality?** YES (ATR-relative, pct-of-leg)

## Verdict

PHASE57B CAUSALITY: **PASS**
PHASE57B CAUSAL TURN EDGE: **NO**
PHASE57B EPISODE ROBUSTNESS: **FAIL**
PHASE57B EXECUTABLE ENTRY: **FAIL**
PHASE57B COST STRESS: **FAIL**
PHASE57B YEAR STABILITY: **FAIL**
PHASE57B PLACEBO: **PASS**
PHASE57B HOLDOUT: **FAIL**
PHASE57B ONE-POSITION PORTFOLIO: **FAIL**
PHASE57B OVERALL: **FAIL**
READY FOR PHASE57C CROSS-MARKET: **NO**
