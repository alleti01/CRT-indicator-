PHASE69 — FROZEN ENTRY EXIT MANAGEMENT
=======================================

ENTRY ENGINE: Phase58D(E) → P4 → H1 KEEP → M1 entry @ next bar open
ENTRY HASH: 0da41f282174679f
ENTRY CHANGED: NO
CAUSALITY: PASS
PREFIX: PASS

CURRENT MANAGEMENT: stop=1.0 ATR | target=2.5R | max hold=60m | STOP_FIRST

----------------------------------------
M0 CURRENT RESULTS
----------------------------------------
N: 36,174
AvgR: 0.0160
PF: 1.023
TotalR: 578.5
MaxDD: 170.2
Win rate: 29.1%
Avg winner: 2.483R
Avg loser: -0.999R
Target exits: 28.8%
Stop exits: 70.7%

----------------------------------------
IS 2.5R TOO LOW?
----------------------------------------
Trades reaching 2.5R: 26,481 (73.2% of all)
Later reach 3R: 20.0%
Later reach 4R: 15.5%
Later reach 5R: 12.6%
Later reach 7R: 8.9%
Later reach 10R: 5.5%
Median additional MFE after 2.5R: 7.26R
P90 additional MFE: 18.62R

ANSWER: MIXED — many trades extend beyond 2.5R but fixed larger targets trade off win rate

----------------------------------------
MARKET OPEN (09:30–10:30 NY)
----------------------------------------
Open 2.5→4R: 16.5%
Open 2.5→5R: 13.3%
Open 2.5→7R: 10.1%
Non-open 2.5→5R: 12.6%
OPEN HAS LONGER RIGHT TAIL: MIXED/NO

----------------------------------------
FIXED TARGET FRONTIER
----------------------------------------
1.5R: AvgR=-0.003 PF=0.99 TotalR=-115 win=39.9%
2.0R: AvgR=0.010 PF=1.02 TotalR=370 win=33.7%
2.5R: AvgR=0.016 PF=1.02 TotalR=578 win=29.1%
3.0R: AvgR=0.019 PF=1.03 TotalR=672 win=25.7%
3.5R: AvgR=0.021 PF=1.03 TotalR=742 win=23.1%
4.0R: AvgR=0.025 PF=1.03 TotalR=904 win=21.3%
5.0R: AvgR=0.033 PF=1.04 TotalR=1195 win=18.7%
6.0R: AvgR=0.043 PF=1.05 TotalR=1553 win=17.3%
7.0R: AvgR=0.041 PF=1.05 TotalR=1490 win=16.4%
8.0R: AvgR=0.049 PF=1.06 TotalR=1754 win=16.0%
10.0R: AvgR=0.059 PF=1.07 TotalR=2123 win=15.6%

BROAD PLATEAU: see frontier table

----------------------------------------
BEST MANAGEMENT CANDIDATES (by TotalR)
----------------------------------------
1. M1_struct_act2: AvgR=0.0798 TotalR=2887 capture=-0.58
2. M5_50_50: AvgR=0.0542 TotalR=1961 capture=-0.58
3. M3_act2.5_gb0.75: AvgR=0.0155 TotalR=559 capture=-0.58

----------------------------------------
HOLDOUT (M0 vs best trail)
----------------------------------------
M0 holdout AvgR: 0.0473
Best holdout AvgR: -0.0527
HOLDOUT IMPROVEMENT: NO

----------------------------------------
FINAL VERDICT
----------------------------------------
NEW EXIT EDGE FOUND: NO / MIXED
BEST MANAGEMENT: M1_struct_act2
INCREMENTAL AVGR: +0.0638
PROMOTE: NO — requires manual review + holdout confirmation
READY FOR PINE: NO
READY FOR LIVE: NO

RECENT TRADE: RECENT TRADE OUTSIDE LOCAL DATA RANGE (data ends ~2026-08-28; Sep 2026 open not in set)

Runtime: 464s