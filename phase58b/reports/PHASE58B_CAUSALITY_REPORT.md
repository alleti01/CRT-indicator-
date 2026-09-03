# Phase58B Causality Report

## Architecture
- 15M context: last completed 15M bar only (aligned to 5M index)
- 5M decision: native 5M bar-close state machine
- 1M execution: activated only after 5M TAKE, max 2 bars delay
- Phase58 v1 untouched (hash verified)
- S54 untouched (hash verified)

## Causal Guarantees
1. Completed 15M only — `htf_bar_index` + forward-fill of last completed bar
2. Completed 5M only — sequential `on_bar_close(j)` on native 5M arrays
3. No HTF lookahead — `align_htf_to_1m` Phase55 convention
4. No future swing — phase52 causal pivot lag
5. No deepest_i — running `pb_extreme` only
6. No future pullback completion
7. No future Leg2
8. Chronological state machine — FiveMTraderEngine
9. Deterministic setup IDs — incremental counter on ARM
10. One trade per active setup — cooldown + structural reset
11. Structural reset — invalidation, opposite sequence, new impulse
12. 5M decision before 1M execution — exec window opens after TAKE bar
13. Max execution delay enforced — 2 bars (X2)
14. Next-bar execution — entry at i+1 open or favorable close
15. Same-bar stop-first — simulation walk priority
16. Truncation invariance — tested
17. Sequential replay — deterministic rerun tested
18. Future labels excluded from features — evaluation modules label-only

PHASE58B CAUSALITY: PASS
