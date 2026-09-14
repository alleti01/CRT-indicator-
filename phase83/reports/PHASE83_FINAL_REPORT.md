# Phase83 — NQ Premarket / Overnight Breakout Acceptance

PHASE83 VERDICT:
PHASE83_VALIDATION_FAIL

DATA:
NQ continuous 1m via `lw_1m_paths` (phase16/18 raw + bridge + phase58j extension). 3,140,775 bars, 2017-10-01 → 2026-09-02. 2,299 RTH sessions (2017-10-03 → 2026-09-02). Stored TZ America/Chicago; sessions in America/New_York. Overnight 18:00 prior trading day → 09:29 ET (mean 930 bars). RTH 09:30–16:00 ET. Costs: NQ $14.50/RT + 0/1/2 tick slip. Mean ON range / 1m ATR ≈ 21.

CAUSALITY:
PASS (500 overnight freeze, 500 2M prefix, 200 decision prefix; 0 failures)

BASELINES:
B0 raw touch — N=2134 net AvgR=+0.045 PF=1.06 WR=32.6% train=+0.028 val=+0.151 test=−0.014 random=+0.068 (real ≉ better than random; test dies)
B1 1M close — N=1988 net AvgR=+0.044 PF=1.06 WR=32.3% train=+0.032 val=+0.065 test=+0.055 random=−0.036
B2 2M close — N=1917 net AvgR=+0.041 PF=1.06 WR=32.1% train=+0.045 val=+0.048 test=+0.020 random=+0.003; timing-matched AvgR=+0.074 (event ≤ open-volatility control)

BEST CONTINUATION:
B2 by train AvgR, but **not promoted**. PF≈1.05, MaxDD 43R, year mix of +/− (2017/18/22/24/26 negative). Timing-matched control is stronger than the breakout itself. B1 looks cleaner vs random but effect size is economically thin and 2-tick slip → AvgR −0.016.

BEST FAILED-BREAK REVERSAL:
F1 wick-fail N=1921 AvgR=+0.002 PF=1.00 train=−0.018. F2/F3 N=1055 AvgR=+0.015 train=−0.046. F4 opposite displacement N=1819 AvgR=−0.001. Failed breaks are **not** more informative than continuation.

RANDOM CONTROL:
B0 random +0.068 > real +0.045. B1 real +0.044 > random −0.036 (sample). B2 real +0.041 > random +0.003. Continuation is not reliably above random once B0 is included; confirmation does not create a new edge.

TIMING CONTROL:
B2 timing-matched +0.074 > real +0.041 — opening-window volatility explains as much or more than the ON-level event.

TRAIN / VALIDATION / TEST:
Chronological 60/20/20 by session date. No model cleared promotion (causality + costs + real>random + real>timing + year stability + meaningful size + val/test). Closest: B1 (+train/+val/+test) still PF 1.06 and slip-fragile. B0 test negative.

LONG / SHORT:
B2 LONG N=1032 AvgR=+0.064; SHORT N=885 AvgR=+0.013. Edge, if any, is long-skewed and small.

COST ROBUSTNESS:
B1 slip0 +0.044 / slip1 +0.014 / slip2 −0.016. B2 slip0 +0.041 / slip1 +0.012 / slip2 −0.016. F1 dead at slip1.

DOES 2M CONFIRMATION ADD VALUE?
NO

DOES VOLUME ADD VALUE?
NO

DOES RETEST ADD VALUE?
NO (B6 AvgR=−0.021; B7 AvgR=−0.092)

ARE FAILED BREAKOUTS MORE INFORMATIVE?
NO

ARE ON HIGH/LOW SPECIAL VS CONTROLS?
NO / INCONCLUSIVE — prior-RTH B1 AvgR=+0.107 and synth open±ON-width B1 AvgR=+0.141 both beat ON B1 +0.044 in-sample. ON levels are not uniquely informative.

PRODUCTION CHANGES:
NONE

NEXT ACTION:
ARCHIVE / STOP

---

**Verdict:** `PHASE83_VALIDATION_FAIL`

PHASE83_MODE = RESEARCH_ONLY
PRODUCTION_MODIFIED = NO
PHASE72A_MODIFIED = NO
PHASE73_MODIFIED = NO
PHASE74_MODIFIED = NO
M0_MODIFIED = NO
PHASE72B_USED_AS_GROUND_TRUTH = NO

## DATA
- Dataset: lw_1m_paths (phase16/18 raw + postwindow bridge + phase58j extension)
- Instrument: NQ continuous 1m
- Contract: vendor continuous / Databento-style roll concatenated; last duplicate kept
- Stored TZ: America/Chicago | Session TZ: America/New_York
- Range: 2017-10-01 17:00:00-05:00 → 2026-09-02 10:48:00-05:00
- Bars: 3140775
- Sessions used: 2299 (2017-10-03 → 2026-09-02)
- Skipped: {'no_rth_open': 0, 'thin_overnight': 0, 'no_prior_rth': 1, 'bad_atr': 0}
- Mean overnight bars: 929.6668116572423
- Mean ON range / ATR: 21.076534068533068
- RTH: 09:30–16:00 ET | Overnight: 18:00 prior trading day → 09:29 ET
- Costs: NQ $14.50/RT (`phase58.research.instrument.NQ`) + 0/1/2 tick slip

## CAUSALITY
- Status: **PASS**
- Overnight freeze checks: 500 fail=0
- 2M prefix checks: 500 fail=0
- Decision prefix checks: 200 fail=0
- Examples: []

## BASELINES
B0 raw touch: B0 N=2134 AvgR=0.04522580009215377 PF=1.0616711893189665 WR=0.32567947516401125 train=0.028373246582682667 val=0.15061666859061493 test=-0.014427898735676521 random=0.06770321234156293
B1 1M close: B1 N=1988 AvgR=0.04352238791332926 PF=1.0594179638440304 WR=0.32344064386317906 train=0.03223520681203955 val=0.0649040072602553 test=0.0546938236722075 random=-0.03580419240178092
B2 2M close: B2 N=1917 AvgR=0.040548194229224704 PF=1.055433855019099 WR=0.32133541992696923 train=0.04465557765326926 val=0.0482693141864804 test=0.0201479206458049 random=0.003198039838452642

## BEST CONTINUATION
BEST_CONT: B2 N=1917 AvgR=0.040548194229224704 PF=1.055433855019099 WR=0.32133541992696923 train=0.04465557765326926 val=0.0482693141864804 test=0.0201479206458049 random=0.003198039838452642

## BEST FAILED-BREAK REVERSAL
BEST_REV: F1 N=1921 AvgR=0.002353370177229756 PF=1.003155154112884 WR=0.3107756376887038 train=-0.01806858910042027 val=-0.011327010844777271 test=0.07564278430116889 random=0.023917764371278485

## RANDOM / FLIPPED / TIMING
See MODEL_RESULTS.csv. Random = 8-seed re-walk at same timestamps. Flipped = opposite direction re-walk.

## LEVEL CONTROL
- ON B1: {'N': 1988, 'WinRate': 0.32344064386317906, 'AvgR': 0.04352238791332926, 'PF': 1.0594179638440304, 'TotalR': 86.52250717169858, 'MaxDD': 38.333423519692616, 'MedianR': -1.0418988648090812, 'GrossAvgR': 0.1297959255415524, 'LONG': 1066, 'SHORT': 922, 'MFE15': 2.6211264500732097, 'MAE15': 2.517131783569907, 'MFE30': 3.5177240118020356, 'MAE30': 3.419295172288475}
- PRIOR RTH B1: {'N': 1791, 'WinRate': 0.34952540480178673, 'AvgR': 0.10660514765325371, 'PF': 1.1473364287724035, 'TotalR': 190.9298194469774, 'MaxDD': 85.92873284253695, 'MedianR': -1.046506300114546, 'GrossAvgR': 0.22157958913297343, 'LONG': 1038, 'SHORT': 753, 'MFE15': 3.7563813045270504, 'MAE15': 3.5227115695509426, 'MFE30': 4.875483589648288, 'MAE30': 4.75002113063183}
- SYNTH (open ± overnight width) B1: {'N': 513, 'WinRate': 0.3489278752436647, 'AvgR': 0.14139476180045912, 'PF': 1.2018875548689885, 'TotalR': 72.53551280363553, 'MaxDD': 20.268047033207544, 'MedianR': -1.0387035271687315, 'GrossAvgR': 0.21580562063132638, 'LONG': 221, 'SHORT': 292, 'MFE15': 2.0519525440160065, 'MAE15': 1.6087846335750708, 'MFE30': 2.8612232299470515, 'MAE30': 2.18282834004247}
- ON special vs controls: INCONCLUSIVE

## COST ROBUSTNESS
{
  "B1": {
    "slip0": 0.04352238791332926,
    "slip1": 0.013772892179459362,
    "slip2": -0.01597660355441055
  },
  "B2": {
    "slip0": 0.04054819422922471,
    "slip1": 0.01245883169802237,
    "slip2": -0.015630530833179966
  },
  "F1": {
    "slip0": 0.0023533701772297934,
    "slip1": -0.026374668064801106,
    "slip2": -0.05510270630683199
  },
  "F2": {
    "slip0": 0.014598490690798547,
    "slip1": -0.011493316075274151,
    "slip2": -0.03758512284134688
  }
}

## STAGE 2
Ran: True

## PROMOTED
NONE

## CORE ANSWERS
1. Raw touch directional info? False
2. 1M close improves? False
3. 2M close improves? False
4. 2M compensates delay? False
5. Body quality? False
6. Volume? False
7. Retest? False
8. Failed breaks more informative? False
9. Fail + opposite displacement? False (F4 AvgR=−0.001)
10. ON high/low special? INCONCLUSIVE
11. Survives costs? True
12. Survives val+test? False
13. Both sides? True
14. Chase (B2 distance buckets): see ANTI_CHASE_B2.csv

## PRODUCTION CHANGES
NONE

## NEXT ACTION
ARCHIVE / STOP

Elapsed: 278.5s
