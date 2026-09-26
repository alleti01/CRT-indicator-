# Phase86 FINAL REPORT

VERDICT: SIDEWAYS_FIX_NO_INCREMENTAL_VALUE

PRODUCTION MODIFIED: NO

CURRENT SKIP_CHOP: 20-bar box < 2 ATR in evaluate_quality_gates (unchanged).

CURRENT SKIP_NO_TREND: |progress| < 0.5 ATR inside `not close_through and not pa_agree`.

CURRENT CONTINUATION LOGIC: pa_agree = 3 of last 4 bodies with the trade.

CURRENT 3-OF-4 BYPASS: YES — pa_agree skips no-trend / false-break / late-move.

EXACT BYPASS LOCATION:
file: phase74/quality/gates.py
function: evaluate_quality_gates
line/branch: if not close_through and not pa_agree: (lines 102-117)

NEW SIDEWAYS STATE: SIDEWAYS_WIDE_RANGE = range_atr>=2 AND efficiency<=0.25 AND overlap>=0.45. Not mixed candles. Not a session ban.

RANGE METRIC: max(high)-min(low) / ATR on last 20 including T.

DIRECTIONAL EFFICIENCY: abs(close_T - close_T-19) / path of closes. 0 if path=0.

OVERLAP: mean adjacent inter/union of candle ranges.

STRUCTURAL PROGRESS: close through frozen pre-break wall, or causal retest-hold. Wick is not progress.

PRE-BREAK BOUNDARY: max/min of bars before T. Decision bar cannot raise the wall.

FALSE BREAK: wick beyond frozen wall, close back inside → PASS_FALSE_BREAK.

ESCAPE ROUTE A: close through frozen wall ± 0 ATR buffer.

ESCAPE ROUTE B: prior close-through, pullback tag, subsequent closes hold outside.

FINAL EVALUATION ORDER: session → SKIP_DATA → SKIP_CHOP/ATR_CAP → sideways → escape → false break → only then 3-of-4 / TAKE. RTH identity.

18-TRADE REPLAY:
N = 18

ORIGINAL (current-gate TAKEs):
wins 8
losses 7
TotalR 9.4432

CANDIDATE:
wins 7
losses 7
TotalR 7.4432

3-OF-4 LOSERS BLOCKED: 0 (incremental). The five reviewed 3-of-4 losers stay TAKE — overlap 0.34-0.43 < 0.45.

MIXED LOSERS BLOCKED: 0 incremental (metrics, not candle color).

WINNERS BLOCKED: ['2026-09-18 08:56 ET SHORT']

KNOWN MIXED WINNER: SKIP reason SKIP_NO_TREND
(live filled +2.43R; current-gate replay is SKIP_NO_TREND; overlay does not add a mixed veto.)

LOSER REJECTION: 0 incremental

WINNER RETENTION: 0.875

NET R DELTA: -2.0

RTH REGRESSION: PASS
changed decisions = 0 of 21

CAUSALITY: PASS
samples = 500
mismatches = 0

LARGER SAMPLE:

BASELINE:
N 37
AvgR 0.3477
PF 1.5848
TotalR 12.8658
MaxDD -7.5

CANDIDATE:
N 32
retention 0.8649
AvgR 0.2458
PF 1.3933
TotalR 7.8658
MaxDD -5.5

REJECTED TRADES:
N 5
AvgR 1.0
TotalR 5.0

LONG baseline {'n': 19, 'wins': 7, 'losses': 12, 'AvgR': 0.2561, 'TotalR': 4.8658, 'PF': 1.4055, 'MaxDD': -4.0, 'win_rate': 0.3684} candidate {'n': 19, 'wins': 7, 'losses': 12, 'AvgR': 0.2561, 'TotalR': 4.8658, 'PF': 1.4055, 'MaxDD': -4.0, 'win_rate': 0.3684}
SHORT baseline {'n': 18, 'wins': 8, 'losses': 10, 'AvgR': 0.4444, 'TotalR': 8.0, 'PF': 1.8, 'MaxDD': -4.5, 'win_rate': 0.4444} candidate {'n': 13, 'wins': 5, 'losses': 8, 'AvgR': 0.2308, 'TotalR': 3.0, 'PF': 1.375, 'MaxDD': -3.0, 'win_rate': 0.3846}

COST ROBUSTNESS:
0 tick baseline {'n': 37, 'wins': 15, 'losses': 22, 'AvgR': 0.3477, 'TotalR': 12.8658, 'PF': 1.5848, 'MaxDD': -7.5, 'win_rate': 0.4054} candidate {'n': 32, 'wins': 12, 'losses': 20, 'AvgR': 0.2458, 'TotalR': 7.8658, 'PF': 1.3933, 'MaxDD': -5.5, 'win_rate': 0.375}
+1 tick (0.25pt / $5 NQ) baseline {'n': 37, 'wins': 15, 'losses': 22, 'AvgR': 0.3135, 'TotalR': 11.5996, 'PF': 1.5109, 'MaxDD': -7.7798, 'win_rate': 0.4054} candidate {'n': 32, 'wins': 12, 'losses': 20, 'AvgR': 0.2124, 'TotalR': 6.7962, 'PF': 1.3292, 'MaxDD': -5.7179, 'win_rate': 0.375}
+2 tick baseline {'n': 37, 'wins': 15, 'losses': 22, 'AvgR': 0.2793, 'TotalR': 10.3335, 'PF': 1.4415, 'MaxDD': -8.0597, 'win_rate': 0.4054} candidate {'n': 32, 'wins': 12, 'losses': 20, 'AvgR': 0.179, 'TotalR': 5.7265, 'PF': 1.2691, 'MaxDD': -5.9358, 'win_rate': 0.375}

PARAMETER STABILITY: overlap is the cliff. 0.55 = no incremental change. 0.45 = skip Fri 8:56 winner only. 0.35 = overfilter (kills Wed 00:27 / 01:55 winners). Buffer 0/0.05/0.10 does not change the week incremental table. Grid frozen after 18-trade inspection; not retuned on the 58-fill sample.

DOES SIDEWAYS DETECTION ADD VALUE? NO

DOES STRUCTURAL ESCAPE PRESERVE RANGE WINNERS? YES on constructed tests; the one incremental skip (Fri 8:56) had no close-through, so escape did not release it (it was a +2R winner the combo still tagged sideways).

DOES 3-OF-4 STILL BYPASS SIDEWAYS? NO in the overlay (tests 1/2/12). YES still in production gates.py because overlay is not wired.

RECOMMENDATION: KEEP CURRENT

NEXT ACTION: leave Globex off and overlay unwired. Do not rescue-tune overlap on this sample. Revisit only with a larger causal opportunity set.
