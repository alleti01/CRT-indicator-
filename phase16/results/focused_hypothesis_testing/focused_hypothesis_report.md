# Focused Hypothesis Testing for Retest-Gated Entry Quality

## Executive summary

The 42-trade reference baseline reproduced exactly (**PASS**). The three preregistered hypotheses were then evaluated on the already-downloaded 2024-01-01 through 2026-06-26 history, now classified as development data. No new data was downloaded, no unseen data was accessed, and no Pine or frozen strategy logic was changed.

Across 93 predefined cells (76 statistically testable), 0 survived Benjamini-Hochberg FDR at 5%. Entry-quality evidence is **WEAK**. **NO QUALITY FILTER SHOULD BE ADDED YET.**

## BASELINE

Reference reproduction: N 42, wins 17, losses 25, WR 40.48%, net AvgR -0.00846, net TotalR -0.35512, net PF 0.98369, net MaxDD 8.37128R — PASS.

Larger development baseline: N 705, gross AvgR -0.03634, gross TotalR -25.62, gross PF 0.9304; net AvgR -0.06957, net TotalR -49.05, net PF 0.8718, net MaxDD 60.30R.

## H1 RESULT

Strongest adequately supported observation (not a selected rule unless every gate passes): **H1_D0.00_V1.75**. N 305 (43.3% retention; BETTER SUPPORTED), net AvgR -0.0068, net TotalR -2.06, net PF 0.9878, net MaxDD 20.82R. Gross AvgR 0.0293, gross PF 1.0551.

Direction: Long N 130, net AvgR 0.1261, PF 1.2593; Short N 175, net AvgR -0.1055, PF 0.8254. Time: 1/3 positive years, 4/10 positive quarters, 1/2 positive halves.

Plateau: NO; realistic costs: NO; outlier removals: NOT APPLICABLE (failed cost-positive prerequisite); time stability: NO; FDR: FAIL (q=0.9900). Overall: NOT PROMISING.

## H2 RESULT

Strongest adequately supported observation (not a selected rule unless every gate passes): **H2_R1.00_C0.30**. N 330 (46.8% retention; BETTER SUPPORTED), net AvgR 0.0221, net TotalR 7.28, net PF 1.0414, net MaxDD 18.74R. Gross AvgR 0.0538, gross PF 1.1045.

Direction: Long N 153, net AvgR -0.0129, PF 0.9761; Short N 177, net AvgR 0.0523, PF 1.0991. Time: 2/3 positive years, 5/10 positive quarters, 1/2 positive halves.

Plateau: NO; realistic costs: YES; outlier removals: NO; time stability: NO; FDR: FAIL (q=0.8444). Overall: NOT PROMISING.

Average delays: BOS→Retest 1.75 bars; Retest→Confirm 1.32 bars.

## H3 RESULT

Strongest adequately supported observation (not a selected rule unless every gate passes): **H3_HIGH_Premarket**. N 139 (19.7% retention; BETTER SUPPORTED), net AvgR 0.0266, net TotalR 3.69, net PF 1.0445, net MaxDD 15.02R. Gross AvgR 0.0559, gross PF 1.0965.

Direction: Long N 64, net AvgR 0.1388, PF 1.2547; Short N 75, net AvgR -0.0692, PF 0.8921. Time: 1/3 positive years, 5/10 positive quarters, 2/2 positive halves.

Plateau: NO; realistic costs: YES; outlier removals: NO; time stability: NO; FDR: FAIL (q=0.9900). Overall: NOT PROMISING.

## Final decision

- Best individual hypothesis: **NONE**
- Robust parameter plateau found: **NO**
- Survives realistic costs: **NO**
- Survives outlier removal: **NO**
- Survives time stability: **NO**
- FDR survivors: **0**
- Entry quality improvement evidence: **WEAK**

No two-hypothesis combination was tested unless an individual hypothesis first met every preregistered success criterion. Quantile/session definitions, the 20-bar causal volume average, and the trailing-100-bar causal ATR percentile were fixed before examining cell outcomes.

## Required conclusion

**NO QUALITY FILTER SHOULD BE ADDED YET.**
