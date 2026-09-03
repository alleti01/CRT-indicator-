PHASE61 — CAUSAL EARLY-SIGNAL & TRADER-JUDGMENT AUDIT
======================================================

CAUSALITY: PASS
PREFIX INVARIANCE: PASS

--------------------------------------------
RAW SIGNAL QUALITY
--------------------------------------------

RAW SIGNALS: 232,121

Directional accuracy:
  1m: 45.9%
  2m: 46.5%
  3m: 46.7%
  5m: 47.1%
  10m: 47.8%
  15m: 48.3%
  30m: 48.6%
  60m: 49.0%
Median MFE 15m: 1.690 ATR
Median MFE 30m: 2.446 ATR
Median MFE 60m: 3.526 ATR
Median MAE 60m: 3.500 ATR
+1 ATR reached: 84.0%
+2 ATR reached: 69.4%
+2.5 ATR reached: 62.6%
+3 ATR reached: 56.2%

--------------------------------------------
OPPORTUNITY CLUSTERING
--------------------------------------------
RAW SIGNALS: 232,121
UNIQUE OPPORTUNITIES: 87,798
REDUNDANCY: 62.2%
MEAN SIGNALS / OPPORTUNITY: 2.64
MEDIAN SIGNALS / OPPORTUNITY: 2

--------------------------------------------
FIRST VS LATER SIGNAL
--------------------------------------------
FIRST: n=87,798 MFE60=3.56 MAE60=3.56 chase=0.42
SECOND: n=54,753 MFE60=3.54 MAE60=3.49 chase=1.30
THIRD: n=34,395 MFE60=3.56 MAE60=3.47 chase=2.43
LAST: n=87,798 MFE60=1.87 MAE60=5.30 chase=1.04
WAITING IMPROVES MFE: NO (15.1%)
MEDIAN PRICE DAMAGE FROM WAITING: 2.50

--------------------------------------------
TRADE PATHS (first-signal opportunities)
--------------------------------------------
LATE_ENTRY: 112,313
WINNER_AFTER_DEEP_PULLBACK: 39,567
DUPLICATE_SIGNAL: 32,010
WRONG_DIRECTION: 17,983
CLEAN_WINNER: 9,261
WINNER_AFTER_SMALL_PULLBACK: 9,242
RIGHT_DIRECTION_BAD_STOP: 4,810
CHASED_ENTRY: 3,934
STALLED: 2,635
REVERSAL_AFTER_PROFIT: 366

--------------------------------------------
FIXED MANAGEMENT (first signal only)
--------------------------------------------
stop_0.75_target_2.0: N=87,798 AvgR=-0.008 PF=0.99 TotalR=-700 MaxDD=881.5
stop_0.75_target_2.5: N=87,798 AvgR=-0.006 PF=0.99 TotalR=-488 MaxDD=903.1
stop_0.75_target_3.0: N=87,798 AvgR=0.000 PF=1.00 TotalR=39 MaxDD=636.9
stop_1.0_target_2.0: N=87,798 AvgR=-0.009 PF=0.99 TotalR=-801 MaxDD=983.6
stop_1.0_target_2.5: N=87,798 AvgR=-0.007 PF=0.99 TotalR=-658 MaxDD=1038.6
stop_1.0_target_3.0: N=87,798 AvgR=-0.005 PF=0.99 TotalR=-477 MaxDD=1024.4
stop_1.25_target_2.0: N=87,798 AvgR=-0.004 PF=0.99 TotalR=-378 MaxDD=649.5
stop_1.25_target_2.5: N=87,798 AvgR=-0.002 PF=1.00 TotalR=-173 MaxDD=536.2
stop_1.25_target_3.0: N=87,798 AvgR=0.002 PF=1.00 TotalR=193 MaxDD=555.0

Baseline 1.0/2.5R: N=87,798 AvgR=-0.007 PF=0.99 TotalR=-658

--------------------------------------------
JUDGMENT HYPOTHESES (50k sample)
--------------------------------------------
H1_not_chased: bad_removed=12752 good_removed=4985 selectivity=2.56 winner_ret=46.0% take=22,967
H2_reaction_quality: bad_removed=261 good_removed=103 selectivity=2.53 winner_ret=98.9% take=49,429
H3_no_htf_conflict: bad_removed=817 good_removed=349 selectivity=2.34 winner_ret=96.2% take=48,166
H4_location_quality: bad_removed=5421 good_removed=2141 selectivity=2.53 winner_ret=76.8% take=38,567
H5_first_signal_only: bad_removed=14621 good_removed=5722 selectivity=2.56 winner_ret=38.0% take=18,913

--------------------------------------------
PRIMARY PROBLEMS
--------------------------------------------
SIGNAL_QUALITY: HIGH
DUPLICATES: MEDIUM
DIRECTION: MEDIUM
ENTRY_TIMING: HIGH
STOP_PLACEMENT: LOW
PROFIT_MANAGEMENT: LOW
CHOP: LOW
CHASE: LOW
OVERFILTERING: LOW

--------------------------------------------
VERDICT
--------------------------------------------
RAW CAUSAL SIGNALS CONTAIN TRADEABLE INFORMATION: YES
PRIMARY FAILURE: duplicates + stop placement + direction noise (see path counts)
SIMPLE JUDGMENT HELPS: YES
HEAVY FILTERING NEEDED: NO
MANAGEMENT DESERVES NEXT PHASE: YES
READY FOR PHASE62: YES