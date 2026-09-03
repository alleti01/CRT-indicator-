PHASE69B — NARROW PARTIAL RUNNER VALIDATION
===========================================

ENTRY HASH: 0da41f282174679f
ENTRY PARITY: PASS
NON-WINNER M0 PARITY: PASS

M0: AvgR=0.0160 PF=1.023 TotalR=578.5 DD=170.2
TRUE 2.5R WINNERS: N=10432 (28.8%)

--------------------------------
PRIMARY MATRIX (full sample net R)
--------------------------------
80/20 + 1.5 → 4.0: AvgR=-0.0102 Δ=-0.0262
80/20 + 1.5 → 5.0: AvgR=-0.0098 Δ=-0.0258
80/20 + 1.5 → 7.0: AvgR=-0.0091 Δ=-0.0251
80/20 + 2.0 → 4.0: AvgR=-0.0066 Δ=-0.0226
80/20 + 2.0 → 5.0: AvgR=-0.0063 Δ=-0.0223
80/20 + 2.0 → 7.0: AvgR=-0.0057 Δ=-0.0217
75/25 + 1.5 → 4.0: AvgR=-0.0168 Δ=-0.0328
75/25 + 1.5 → 5.0: AvgR=-0.0163 Δ=-0.0323
75/25 + 1.5 → 7.0: AvgR=-0.0154 Δ=-0.0314
75/25 + 2.0 → 4.0: AvgR=-0.0123 Δ=-0.0283
75/25 + 2.0 → 5.0: AvgR=-0.0119 Δ=-0.0279
75/25 + 2.0 → 7.0: AvgR=-0.0111 Δ=-0.0271

--------------------------------
TRAIN TOP 3
--------------------------------
1. 80/20_1.5R_4R_h60: ΔAvgR=-0.0267 score=-999.00
2. 80/20_1.5R_5R_h60: ΔAvgR=-0.0271 score=-999.00
3. 80/20_1.5R_7R_h60: ΔAvgR=-0.0261 score=-999.00

--------------------------------
VALIDATION
--------------------------------
M0 Δ baseline: 0
80/20_1.5R_7R_h60: ΔAvgR=-0.0242
80/20_1.5R_5R_h60: ΔAvgR=-0.0244
80/20_1.5R_4R_h60: ΔAvgR=-0.0253

SELECTED: 80/20_1.5R_4R_h60

--------------------------------
PREVIOUSLY EXPOSED HOLDOUT
--------------------------------
M0 AvgR: 0.0473
Selected AvgR: 0.0218
ΔAvgR: -0.0255
SUPPORTIVE: NO
PRISTINE: NO

--------------------------------
SELECTED RUNNER
--------------------------------
Split: 80/20  Protection: 1.5R  Target: 4.0R
AvgR: -0.0102  PF: 0.986  TotalR: -369.5  DD: 602.0
ΔAvgR: -0.0262  ΔTotalR: -948.0

RUNNER OUTCOMES:
  Target hit: 21.6%
  Protection hit: 77.9%
  Timeout: 0.5%
  Final >2.5R: 21.9%
  Final ≥3R: 0.0%
  Final ≥4R: 0.0%

M0 DAMAGE:
  <2.4R: 78.0%
  <2.25R: 0.0%
  <2.0R: 0.0%

ATTRIBUTION:
  M0 TotalR: 578.5
  Runner extra profit: 679.5
  Runner giveback: 1627.1
  Extra costs: 0.3
  Net increment: -948.0  Residual: 0.00

BOOTSTRAP ΔAvgR 95% CI:
  [-0.0274, -0.0250]

--------------------------------
CENTRAL ANSWERS
--------------------------------
DOES SMALL RUNNER ADD EXPECTANCY: NO (all 12 primary variants ΔAvgR < 0)
IS 80/20 BETTER THAN 75/25: YES (less damage, but still negative)
IS 1.5R PROTECTION BETTER: NO (2R protection less harmful)
IS 5R A REASONABLE RUNNER TARGET: NO (target hit 15–22%; protection dominates)
DOES RUNNER DAMAGE TOO MANY M0 WINNERS: YES (~78–97% final R < 2.4 vs M0 2.5 lock)
DO COSTS ERASE THE EDGE: NO (costs tiny; giveback is the issue)

WHY: 78–97% of true winners hit runner protection (1.5R or 2R) before target.
Weighted exit ≈ 2.30R (1.5 prot) or 2.40R (2R prot) vs M0 2.50R lock.
Runner target hits (4–7R) too rare to offset systematic winner giveback.

BEST (LEAST HARMFUL) VARIANT: 80/20 + 2R stop + 7R target (ΔAvgR = -0.0217)

--------------------------------
FINAL VERDICT
--------------------------------
PARTIAL RUNNER EDGE: NO
STATUS: NO_PARTIAL_RUNNER_EDGE
EXPOSED HOLDOUT: NOT_SUPPORTIVE

CHANGE M0 LIVE: NO
READY FOR PINE: NO
READY FOR LIVE: NO
READY FOR FORWARD FREEZE: NO

NEXT STEP: Keep M0 as live benchmark. Do not deploy partial runner.