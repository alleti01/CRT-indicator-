# Phase 35 — NQ 15M Historical LONG/SHORT Entry Re-Discovery

**Label:** DEVELOPMENT / DISCOVERY  
**Period:** 2018-01-01 → 2026-06-26 (America/Chicago RTH 09:30–16:00)  
**Lookahead audit:** PASS — future data used only for labels; all features and signals are causal.

---

## 1. Direct Answers

### Where should the indicator say LONG?

Historically favorable long entries cluster at **early-session volatility expansion with elevated relative volume**, not generic positive momentum:

**Frozen walk-forward simple rule (fold 7):**
```
atr_expansion > 1.145
AND minutes_since_open < 75
AND rel_volume > 1.392
```

Interpretation: first ~75 minutes of RTH, when ATR is expanding vs 5 bars ago and volume exceeds its 20-bar average, long entries had modestly higher STRONG-label density in training — but this did **not** produce positive net walk-forward expectancy.

### Where should the indicator say SHORT?

Short opportunities were more **structure-linked** than long:

**Frozen walk-forward simple rule (fold 7):**
```
atr_expansion > 1.145
AND break_low_8 > 0
```

Interpretation: breakdown below the prior 8-bar low during volatility expansion. Reversal-specific features (failed displacement, midpoint reclaim, wick rejection) appeared in ML trees but did not survive as stable simple rules with positive OOS economics.

### What distinguishes good entries from bad ones?

| Signal tier | Long precision | vs baseline 16.5% | Short precision | vs baseline 18.2% |
|-------------|---------------:|------------------:|----------------:|------------------:|
| Top 50% ML score | 19.8% | 1.24× | 22.1% | 1.24× |
| Top 10% | 23.7% | 1.48× | 26.2% | 1.47× |
| Top 2% | 24.8% | 1.55× | 28.9% | 1.62× |
| Top 1% | 23.5% | 1.47× | 27.7% | 1.54× |

**Key finding:** Modest separability exists (~1.5× lift at the extreme tail) but precision is **not monotonic** as score rises (top 2% beats top 1% on both sides). Simple 2–3 condition rules capture more STRONG opportunities than Phase 31/33 but with **negative** net AvgR — i.e., they add false positives faster than true positives.

---

## 2. Historical Opportunity Landscape

| Metric | Long | Short |
|--------|-----:|------:|
| Total RTH decision bars | 54,851 | 54,851 |
| STRONG opportunities (+2R before −1R, 0.75 ATR stop, 60m) | 9,028 | 9,963 |
| Baseline STRONG rate | 16.5% | 18.2% |
| GOOD opportunities (+1.5R before −1R) | 6,058 | 5,345 |

Ambiguous intrabar paths: **stop before target** (conservative).

Full labeled bar-level outcomes: `historical_entry_opportunities.csv`  
STRONG/GOOD opportunity list: `historical_strong_good_opportunities.csv`

---

## 3. Walk-Forward Discovery (stitched OOS only)

**Execution model:** CURRENT bar close entry, 0.75 ATR stop, 2.0R target, 60-minute horizon, $14.50 RT cost.

| Metric | Combined | Long | Short |
|--------|----------|------|-------|
| N | 5,560 | 4,191 | 1,369 |
| Trades/day | ~2.8 | ~2.6 | ~2.2 |
| Win rate | 36.7% | 37.2% | 35.2% |
| Net AvgR | **−0.036R** | **−0.037R** | **−0.032R** |
| PF | 0.94 | 0.94 | 0.95 |
| MaxDD | 241.5R | 193.1R | 82.6R |

**Success gates:** FAIL on AvgR, PF, cost stress, 2024–2025, monotonic precision, exclude-top-1% robustness.

---

## 4. Entry Timing (matched STRONG events)

| Model | Long fill | Long AvgR | Short fill | Short AvgR |
|-------|----------:|----------:|-----------:|-----------:|
| CURRENT (bar close) | 100% | +2.00R* | 100% | +2.00R* |
| NEXT_OPEN | 100% | +1.93R | 100% | +1.87R |
| NEXT_CLOSE | 100% | +1.09R | 100% | +1.00R |
| RETRACE_25 | 44% | +1.97R | 43% | +1.92R |
| RETRACE_50 | 15% | +1.93R | 15% | +1.89R |

\*Label-aligned geometry; not net of costs. Retest entries show **no matched-event improvement** — lower fill without better R on filled subset.

**Best causal timing:** bar close (CURRENT) or next-bar open; avoid retest-only entries for this geometry.

---

## 5. Yearly Robustness

| Year | N | Net AvgR | PF |
|------|--:|---------:|---:|
| 2020 | 1,086 | −0.023R | 0.96 |
| 2021 | 1,060 | −0.077R | 0.88 |
| 2022 | 816 | −0.019R | 0.97 |
| 2023 | 720 | **+0.057R** | 1.10 |
| 2024 | 756 | −0.068R | 0.89 |
| 2025 | 749 | −0.110R | 0.83 |
| 2026 | 373 | **+0.041R** | 1.07 |

Negative in 4 of 7 reported years; 2024–2025 collapse is a major concern.

---

## 6. Cost Stress

| Multiplier | Net AvgR | PF |
|------------|----------|-----|
| 1.0× ($14.50) | −0.036R | 0.94 |
| 1.5× | −0.051R | 0.92 |
| 2.0× | −0.065R | 0.90 |

---

## 7. Phase 31 / 33 Benchmark Comparison

**STRONG opportunity capture rate** (exact timestamp match):

| System | Long capture | Short capture |
|--------|-------------:|--------------:|
| Phase 31 MOMENTUM_DISPLACEMENT | 4.2% | 4.3% |
| Phase 33 REVERSAL | 1.6% | 1.6% |
| Phase 35 discovered rules | **11.4%** | 3.7% |

Phase 35 long rule catches ~2.7× more STRONG long bars than Phase 31, but walk-forward economics are negative — the incremental capture is mostly **false positives**.

**Benchmark walk-forward (prior phases, stitched OOS):**
- Phase 31: Net AvgR ≈ **+0.23R**, PF > 1.35
- Phase 33: Net AvgR ≈ **+0.18R**, PF > 1.35

Phase 35 does **not** beat either benchmark on expectancy despite higher long opportunity recall.

---

## 8. Reversal / Failed-Displacement Investigation

Causal reversal features were engineered (`mid_reclaim_up/down`, `disp_long/short`, wick ratios, pullback depth, break failures). In walk-forward trees they appeared intermittently (e.g., `pullback_from_high_8`, `dist_high_8_atr` for shorts) but:

- Did not stabilize into cross-fold simple rules
- Did not produce a dedicated reversal entry mechanism with positive OOS AvgR
- Phase 33's explicit failed-displacement state machine remains superior for reversal economics

**Conclusion:** Observable reversal precursors exist weakly in feature space but are **not** sufficient alone for a simple causal LONG/SHORT replacement system.

---

## 9. Classification

| Gate | Result |
|------|--------|
| N ≥ 500 | PASS (5,560) |
| Net AvgR ≥ +0.15R | **FAIL** (−0.036R) |
| PF ≥ 1.35 | **FAIL** (0.94) |
| Positive at 1.5× / 2.0× cost | **FAIL** |
| 2024–2026 positive | **FAIL** (2024–2025 negative) |
| Both halves positive | **FAIL** |
| Exclude top 1% positive | **FAIL** |
| Monotonic precision curve | **FAIL** |

**FINAL CLASSIFICATION: D** — Discovery complete; no viable replacement/augmentation system met success gates.

---

## 10. Recommendations

1. **Do not replace** Phase 31 continuation or Phase 33 reversal with Phase 35 simple rules.
2. **Do not augment** with the current discovered rules — negative expectancy and regime fragility.
3. **Keep Phase 31/33** as primary architectures; Phase 35 confirms their selectivity was economically necessary.
4. **Next step:** If pursuing entry refinement, constrain search to **Phase 31/33 event windows only** (conditional entry timing / filter within known setups) rather than bar-universe rediscovery — or explore non-symmetric long/short filters at ≤0.5 trades/day with stricter precision floors.

---

## Deliverables

All files in `phase35/results/entry_rediscovery/` including `research_manifest.json`, CSVs, and `ENTRY_REDISCOVERY.xlsx`.
