# CDX V3 Pro — behavioral reconstruction (discovery)

This is **not** the original CDX source. It is a labeled discovery package plus an untested causal hypothesis.

## VERDICT

`CDX_RE_INSUFFICIENT_INFORMATION`

## SCREENSHOTS ANALYZED

12 unique charts (13 files; one duplicate dropped). Sep 6–21, 2026. NQ1! 1m.

## HIGH-CONFIDENCE SIGNALS

0  
(no signal sat on a crosshair with an exact printed minute)

## MEDIUM-CONFIDENCE SIGNALS

10

## LOW-CONFIDENCE SIGNALS

26

## LONG SIGNALS

15

## SHORT SIGNALS

21

## OHLCV SOURCE

`phase58j.research.lw_data.load_market_1m_lw`  
2017-10-01 17:00 CT → **2026-09-02 10:48 CT**  
3,140,775 bars. **No overlap with CDX labels.**

## TIMEFRAME

1m

## HTF TABLE USED

NO. Visible CDX HTF bias treated as `UNTRUSTED_FOR_HISTORICAL_LABELING`.

## TOP DISCRIMINATING FEATURES

Cannot rank vs non-signal bars. All CDX dates lack OHLCV.

Visual (not statistical):

1. Distance to recent rolling high/low
2. Rejection wick / close location
3. Immediate prior impulse then fail
4. Opposite-signal reset after a failed first print
5. Session: many globex/overnight prints

## DISCOVERED SIGNAL FAMILIES

1. Local-extreme reversal  
2. Failed-bounce fade  
3. Same-direction repeat  
4. Overnight/globex extremes  

Not adopted: generic mid-range breakout.

## BEST CANDIDATE LONG RULE

Near 20-bar low + lower-wick rejection + bullish close + 8-bar same-dir cooldown (`apply_candidate_v1`). Exploratory only.

## BEST CANDIDATE SHORT RULE

Mirror at 20-bar high.

## STATE / COOLDOWN LOGIC

Opposite allowed quickly. Same-direction cooldown hypothesized ~8 bars. Not one-per-session. Arming untested.

## SCREENSHOT SIGNAL PARITY

CDX signals: 36 labeled (10 usable for future exact-bar score)  
Exact same-bar matches: 0 (no data)  
±1 bar matches: 0  
Missed: 36 unmatched  
Extra: n/a  
Wrong direction: n/a  
Exact recall / precision / F1: not scored  
RTH (MEDIUM): 3  
OVERNIGHT (MEDIUM): 7

## CAUSALITY

PASS (reconstruction engine, 500 bars)

## REPAINT STATUS

UNKNOWN

## FORWARD VALIDATION

NOT STARTED — `forward/forward_signal_log.csv` ready

## CURRENT SYSTEM COMPARISON

NOT YET. Phase72A paper baseline left untouched. No P&L contest.

## PRODUCTION MODIFIED

NO

## RECOMMENDATION

CONTINUE FORWARD VALIDATION is blocked on **data**. First extend NQ 1m through at least 2026-09-21, rematch MEDIUM labels, then freeze V1 only if HIGH+MEDIUM exact/±1 parity is actually measured.

## NEXT ACTION

1. Append trustworthy NQ 1m (same continuous construction) for Sep 2 → now.  
2. Re-run `python3 -m cdx_research.python.run_cdx_research`.  
3. Log every new CDX LONG/SHORT into `forward/forward_signal_log.csv` (or alerts).  
4. Repaint test on the next live print.  
5. Do not wire this to Phase85 / funded.

## Performance panel (annotation only)

WIN RATE 79.4% / AVG RUNNER +6.53R / TARGET 0.9R / TRADES 46 / WINS 27 / LOSSES 7.  
27+7 ≠ 46 — incomplete accounting; not used as truth.
