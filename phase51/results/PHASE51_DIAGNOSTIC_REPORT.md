# Phase51 Diagnostic Report

## Signal pipeline

- **Trading logic unchanged vs Phase50:** YES
- **barstate.isrealtime in script:** NO
- **Model hash (frozen):** `f29e61a82ef19fe21e13aa040035ca7bcabf7504f0477ebc4643253f7fd6f1f0`

## 15M data alignment audit

| Feature | Trading bundle | Diagnostic / security |
|---------|------------------|------------------------|
| OHLC / barBody / barRange / closeLoc | CHECK | CHECK |
| ATR (ta.atr) | 15M | 15M |
| displacement (body vs avgBody) | CHECK | CHECK |
| impulse (3-bar / ATR) | 15M | 15M |
| CRT close location (FZ_CL_LONG/SHORT) | CHECK | 15M |
| quality score (qualityRaw/qualityPass) | 15M | 15M |
| RTH session (inRth) | 15M | 15M |
| dedupe (dedupePass) | 15M | 15M |
| Phase31/33 state machine | CHECK | CHECK |
| request.security #1 (phase44ExportBundle) | 15 | PASS |

**15M DATA ALIGNMENT:** PASS

## 15M close timing (canonical Phase45)

- Phase44 marker time = closed 15M bar open `time` from `phase44ExportBundle`
- B1 actionable = marker + **15 minutes** (`P50_CHART_15M_MIN`)
- B1 window end = actionable + **10 minutes** (`P50_B1_WINDOW_MIN`)
- No extra 15-minute delay beyond the frozen post-marker wait

**15M CLOSE TIMING:** PASS (matches Python `confirm_b1` start_ts = actionable)

## Phase44 gate model (per closed 15M bar)

Seven instantaneous gates evaluated on native 15M data:

1. **RTH** — regular trading hours
2. **DISPLACEMENT** — body > 1.5× 20-bar average body
3. **CRT** — close location ≥ 0.80 (long) or ≤ 0.20 (short)
4. **ATR** — valid ATR(14) > 0
5. **IMPULSE** — |close−close[3]|/ATR ≥ 0.65
6. **QUALITY** — simple-score ≥ pass threshold
7. **DEDUPE** — frozen dedupe caps

**Important:** Trading Phase44 also requires **BOS retest fill** on a subsequent 15M bar
(Phase31/33 state machine). Passing 7/7 gates on a displacement bar means
`INSTANT GATES PASS` but trading P44 may still fire 1–2 bars later on retest.

## Why obvious moves often produce no entry

**Primary cause: PHASE44 SELECTIVITY (by design)**

Most visible NQ impulses fail one or more of:

- **IMPULSE** — move over 3 bars vs ATR below 0.65 threshold
- **DISPLACEMENT/CRT** — candle body/close-location pattern not met
- **QUALITY** — directional simple-score below pass minimum
- **RTH** — outside 09:30–16:00 CT
- **DEDUPE** — same-direction/day caps

Even when 7/7 gates pass, **B1 only activates after trading Phase44** fires
(BOS retest), not merely on a displacement-looking 15M bar.

**Type A (NO PHASE44):** Large move, no Phase44 context → B1 never evaluated.
Check bottom-left **PHASE44 DIAGNOSTIC** dashboard for last closed 15M gate failures.

**Type B (PHASE44 / NO B1):** Phase44 fired, no micro-BOS within 10 minutes.
Count ≈ `EXPIRED` on debug dashboard / `FORWARD EXPIRED` after forward start.

## RAW B1 diagnostic

Enable **Opportunity Diagnostic Mode** + **Show RAW B1 markers**.
Dashboard row `RAW B1 / auth / noauth` shows how often 1M micro-BOS fires
without Phase44 authorization vs during an open B1 window.

## Pine/Python parity

**PHASE44 PINE/PYTHON PARITY:** BLOCKED BY DATA (no overlapping 15M CSV in repo)

When data exists, run gate comparison via exported `DG_*` plots or Phase49 forward CSV.

## Trading logic changed

**NO** — diagnostics isolated in `phase44DiagnosticBundle()` and 1M opp-diag block.
