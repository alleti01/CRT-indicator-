# PHASE59I — HTF CAUSALITY / FUTURE-LEAKAGE AUDIT (FAST PATH)

## Verdict summary

```
PHASE59I — HTF CAUSALITY / FUTURE-LEAKAGE AUDIT
================================================

5M PYTHON ALIGNMENT: align_htf_to_1m + htf_bar_index — ffills current-period label with precomputed full-bucket OHLC
15M PYTHON ALIGNMENT: same mechanism on 15M resample

5M CLASSIFICATION: C — FUTURE LEAKAGE / LOOKAHEAD
15M CLASSIFICATION: C — FUTURE LEAKAGE / LOOKAHEAD (same root cause)

FUTURE INFORMATION FOUND: YES — at 13:40 Chicago Python receives final 13:40–13:44 5M H/L/C before those 1M bars occur
FIRST FUTURE-LEAK EXAMPLE: 5M HIGH=29298.0 first knowable 13:42; Python supplies it at 13:40

--------------------------------------------
AUG 26 13:40 PROOF
--------------------------------------------

13:40–13:44 1M BARS: see phase59i_fast_audit.json

5M FINAL O: 29292.00 — FIRST KNOWABLE: 2026-08-26 13:40:00-05:00
5M FINAL H: 29298.00 — FIRST KNOWABLE: 2026-08-26 13:42:00-05:00
5M FINAL L: 29288.00 — FIRST KNOWABLE: 2026-08-26 13:43:00-05:00
5M FINAL C: 29295.00 — FIRST KNOWABLE: 2026-08-26 13:44:00-05:00

PYTHON VALUES @ 13:40: O=29292.00 H=29298.00 L=29288.00 C=29295.00
LAST COMPLETED VALUES @ 13:40: O=29297.25 H=29299.75 L=29290.00 C=29292.00
DEVELOPING VALUES @ 13:40: O=29292.00 H=29293.75 L=29288.50 C=29293.50

CAN FINAL 13:40 5M OHLC BE KNOWN @ 13:40: NO

--------------------------------------------
LAST-WEEK 126 TRADE COMPARISON (FAST)
--------------------------------------------

ORIGINAL (frozen CSV): N=126 LONG=62 SHORT=64 AvgR=0.528 PF=1.94 TotalR=66.5

CAUSAL A: N=63 exact=10 ±1m=14 ±5m=27 lost=99 new=36
CAUSAL B: N=130 exact=35 ±1m=44 ±5m=77 lost=49 new=53

LW-063138 ORIGINAL: {'found': True, 'direction': 'LONG', 'entry_ts': '2026-08-26 13:41:00-05:00', 'entry_price': 29293.25, 'signal_i': 3134045, 'stop_m1': 29286.571428571428, 'target_m1': 29309.946428571428, 'exit_reason_m1': 'TARGET'}
LW-063138 CAUSAL A: {'found': False}
LW-063138 CAUSAL B: {'found': False}

--------------------------------------------
TRADINGVIEW
--------------------------------------------

lookahead_off: CAUSAL A equivalent (last completed HTF) — live-safe
lookahead_on: matches frozen Python on historical bars — exposes future-completed bucket early; NOT live-safe
PHASE59H lookahead_on LIVE-SAFE: NO
REPAINT RISK: YES (HTF context changes when bucket completes; signals can shift ~5 bars)

PHASE59H PARITY TARGET VALID: NO (target reproduces leaked HTF semantics)

CORRECT NEXT ARCHITECTURE: CAUSAL A for live TV parity; CAUSAL B optional research path

CANONICAL FILES MODIFIED: NO
FULL HISTORICAL COMPARISON: PENDING (run phase59i_audit.py --full in background)
Elapsed fast path: 708.8s
```
