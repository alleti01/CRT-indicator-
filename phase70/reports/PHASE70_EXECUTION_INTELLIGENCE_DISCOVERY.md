PHASE70 — EXECUTION INTELLIGENCE DISCOVERY
==========================================

SIGNAL HASH: 0da41f282174679f
SIGNAL CHANGED: NO
N SIGNALS: 36,174
CAUSALITY: PASS
PREFIX: PASS

M0 BASELINE: N=36,174 AvgR=0.0160 PF=1.023
TotalR=578.5 MaxDD=170.2 Median hold=3m

----------------------------------------
A — LATE / CHASE DEFENSE
----------------------------------------
Do extended signals perform worse: YES

  LOW_EXTENSION: N=8,932 AvgR=0.067 target%=30.4%
  MEDIUM_EXTENSION: N=9,254 AvgR=0.022 target%=29.0%
  HIGH_EXTENSION: N=9,138 AvgR=-0.006 target%=28.2%
  EXTREME_EXTENSION: N=8,850 AvgR=-0.020 target%=27.7%

PASS_LATE candidate (pass HIGH+EXTREME): NO
  (rejects 50% signals — fails retention gate)
EXTREME-only filter retained: 75.5%
Signals retained: 50.3%
AvgR TAKEN (M0 gross proxy): 0.044
AvgR PASSED: -0.013
FINAL: NO_LATE_FILTER_EDGE

----------------------------------------
B — TIME / PROGRESS
----------------------------------------
Median time winner → +0.25R: 1.0
Median time winner → +0.5R: 1.0
Median time winner → +1R: 2.0
+0.25R within 5m: 92.7%
+1R within 10m: 83.2%

Best no-progress: T5 ΔAvgR=+0.0011
  killed winners: 0.7%  val_inc: +0.0039
FINAL: TIME_EXIT_EDGE
(T5: after 15m, MFE < +1R → exit; marginal +0.0011 AvgR, +41 TotalR vs M0)

UNIFIED CANDIDATE: T5 time/progress only (no entry filter, no failure, no reversal)

----------------------------------------
C — FAILURE EXIT
----------------------------------------
Best failure rule: F1 ΔAvgR=-0.0586
Full stop rate: 37.1% vs M0 70.7%
Killed winners: 5.2%
FINAL: NO_FAILURE_EXIT_EDGE

----------------------------------------
D — REVERSAL
----------------------------------------
EXIT_AND_REVERSE N: 18619  AvgR: 0.0553
Blind flip AvgR: 0.0553
Reversal beats blind: NO
FINAL: NO_REVERSAL_EDGE

----------------------------------------
CENTRAL QUESTIONS
----------------------------------------
ARE CURRENT SIGNALS USABLE: YES (M0 +0.016 AvgR)
ARE SOME SIGNALS TOO LATE: YES
CAN LATE SIGNALS BE IDENTIFIED CAUSALLY: YES
CAN FALSE SIGNALS BE EXITED EARLY: PARTIAL/NO
DO WINNERS PROVE THEMSELVES FASTER: YES (most +0.25R within minutes)
DOES TIME INVALIDATION HELP: YES
CAN NORMAL PULLBACK BE DISTINGUISHED FROM REVERSAL: PARTIAL (needs Phase71)
DO REVERSALS BEAT BLIND FLIPPING: NO

----------------------------------------
FINAL VERDICT
----------------------------------------
LATE DEFENSE: REJECT
TIME/PROGRESS: KEEP
FAILURE EXIT: REJECT
EXIT_AND_REVERSE: REJECT
UNIFIED EXECUTION INTELLIGENCE: PASS
READY FOR PHASE71: YES
READY FOR PINE: NO
READY FOR LIVE: NO

RECENT TV: RECENT_TV_EXAMPLE_OUTSIDE_LOCAL_DATA

NEXT STEP: Phase71 unified trader state machine for surviving components only.