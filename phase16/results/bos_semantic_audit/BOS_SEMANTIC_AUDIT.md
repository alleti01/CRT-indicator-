# BOS Semantic / Market-Structure Audit

## Executive finding

The frozen baseline reproduced exactly, and the frozen Pine/Python files were not changed. The event called `BOS` in the research funnel is a real close break of the most recently confirmed, unused 5-left/5-right pivot in the trade direction. It is causally knowable: the pivot is activated only after five right-side bars close, and every audited break occurred later than that confirmation. However, it is not normally an *independent stage after Setup*: Phase 5 is itself allowed to create Setup from that same directional break event, and Phase 12 immediately consumes the still-true event on the same completed candle. The result is a structurally meaningful but heavily overlapping stage.

**Final classification: B — CURRENT BOS IS PARTIALLY REDUNDANT.**

## 1. Frozen baseline guard

- Coverage: FULL DATA; bars in window: 176,022.
- Trades: 705; exact field mismatches against archived frozen baseline: 0.
- Same-bar Setup+BOS: 664 (94.18%); delayed: 41.
- Net AvgR: -0.06957; TotalR: -49.0491; PF: 0.8718; MaxDD: 60.2967R.

## 2. Exact current BOS definition

Pine (`outputs/CRT_Core_RETEST_GATED_LIVE.pine`, lines 471–477) and Python (`phase16/structure.py`, lines 35–50) match:

```text
LONG break  = finite(active 5/5 pivot high) AND NOT high_used AND close > active_high
SHORT break = finite(active 5/5 pivot low)  AND NOT low_used  AND close < active_low
if both directional breaks occur on one bar: cancel both
```

The frozen setting is `structureBreakMode = Close`; a wick alone cannot trigger it. No displacement, body-size, volume, session-boundary, CRT-boundary, or setup-candle-high/low requirement is part of BOS. The reference is the most recent confirmed local 5/5 pivot high (long) or low (short). A pivot at T becomes known only after T+5 closes. Break detection runs before same-bar pivot ingestion, so a just-confirmed pivot cannot be broken on its own confirmation bar. A level is consumed after one break.

The Phase 12 funnel treats both trend BOS and CHoCH break events as its `BOS` event. Among the 705 trades, 301 were trend-labelled Phase 3 BOS and 404 were Phase 3 CHoCH.

Long and short are exact mirrors. `active_high[1]` / `active_low[1]` in Pine, and `previous_active_high` / `previous_active_low` in Python, preserve the level actually broken before any same-bar pivot update.

## 3. Why Setup and BOS collapse

Phase 5 defines `newLongEvt = bullBreakEvent OR SSL sweep` and `newShortEvt = bearBreakEvent OR BSL sweep`. For all 664 same-bar trade paths, the canonical Setup included the same matching structure-break event. Phase 12 then starts `WAIT_BOS` and, because the BOS check is a separate `if` rather than `else if`, consumes that event on the same bar. This is the combined A+D mechanism in the requested examples.

- Matching break only: 657 / 664.
- Matching break plus liquidity sweep: 7 / 664.
- Reference already crossed on the prior bar: 0 / 664.
- Reference derived from setup candle: 0.

Thus same-bar behavior is not caused by lookahead, a stale pre-crossed threshold, or a setup-derived level. It is caused by event reuse plus top-to-bottom state-machine ordering.

## 4. Independent confirmed-swing audit

| Timing | Swing | N | % | No break |
| --- | --- | --- | --- | --- |
| Same-bar | 2/2 | 502 | 75.60 | 162 |
| Same-bar | 3/3 | 577 | 86.90 | 87 |
| Same-bar | 5/5 | 664 | 100.00 | 0 |
| Delayed | 2/2 | 31 | 75.61 | 10 |
| Delayed | 3/3 | 38 | 92.68 | 3 |
| Delayed | 5/5 | 41 | 100.00 | 0 |

All 705 current events broke their own causal 5/5 reference by definition. Relative to independently replayed causal pivots, 533/705 also fired a 2/2 break and 615/705 also fired a 3/3 break. Each diagnostic pivot was unavailable until its right-side bars closed; the audit asserts confirmation bar < break bar.

Outcome splits for Break vs No break, including Win%, AvgR, median, TotalR, PF, MFE, and MAE, are in `bos_swing_quality.csv`. The notable diagnostic result is not a candidate filter: under 3/3, the 90 'No break' trades were positive while the 615 'Break' trades were negative, which is contrary to a simple 'more structural equals better' thesis.

### Delayed Setup→BOS distribution

| setup_to_bos_bars | N | net_win_rate_pct | net_AvgR | net_median_R | net_TotalR | net_PF | avg_MFE_R | avg_MAE_R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 6+ | 17 | 35.2941 | -0.1151 | -1.0167 | -1.9562 | 0.8292 | 1.1053 | 0.8791 |
| 2 | 7 | 57.1429 | 0.0997 | 0.3938 | 0.6981 | 1.2229 | 1.1026 | 1.1306 |
| 4-5 | 9 | 11.1111 | -0.7086 | -1.0274 | -6.3777 | 0.1294 | 0.5055 | 1.0133 |
| 1 | 5 | 60.0000 | 0.5389 | 0.8383 | 2.6946 | 2.3028 | 1.1630 | 0.5447 |
| 3 | 3 | 33.3333 | -0.6189 | -1.0268 | -1.8568 | 0.1089 | 0.5279 | 1.4840 |

The delayed cohort is only 41 trades and should not be overinterpreted.

## 5. Event-sequence audit

- Setup == BOS: 664 / 705 (94.18%).
- BOS == Retest: 0; Retest == Confirm: 0.
- Confirm == Entry: 705 / 705 (100%).
- Setup == BOS == Retest: 0; BOS == Retest == Confirm: 0.

Retest is always after BOS and confirmation is always after retest. Setup and BOS are not separate for 94.18% of realized trades; Confirm and Entry are intentionally the same close. Full bar-gap distributions are in `bos_event_order_summary.csv`.

## 6. BOS redundancy

- P(BOS same bar | Setup eventually becomes Confirm trade): 664/705 = 94.18%.
- P(BOS same bar | all 3,355 canonical valid setups): 2277/3355 = 67.87%.
- Later matching BOS under the frozen evaluation order: 120/3355 = 3.58%.
- Never/opposite first: 958/3355 = 28.55%.

Classification: **HIGH redundancy on realized trade paths; partial redundancy across all canonical setups.** The >80% threshold is met for setups that become trades, and the code directly reuses the same Boolean. Across all canonical setups, immediate overlap is below 80%, so BOS still changes candidate survival outside the realized-trade cohort.

## 7. Later-only structural-BOS counterfactual

Research-only rule: after Setup, wait for a later close-break event against the most recently causally confirmed 2/2, 3/3, or 5/5 opposing swing; then use that structural level in the unchanged retest, confirmation, entry, ATR stop, 2R target, costs, maximum holding period, expiry, and evaluation ordering.

| model | retention_pct | N | net_wins | net_losses | net_win_rate_pct | net_AvgR | net_median_R | net_TotalR | net_PF | net_MaxDD_R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Current BOS 5/5 (same-bar allowed) | 100.0000 | 705 | 284 | 421 | 40.2837 | -0.0696 | -0.6616 | -49.0491 | 0.8718 | 60.2967 |
| Structural BOS 2/2 (later only) | 36.1702 | 255 | 110 | 145 | 43.1373 | 0.0148 | -0.3586 | 3.7697 | 1.0291 | 23.9798 |
| Structural BOS 3/3 (later only) | 23.4043 | 165 | 71 | 94 | 43.0303 | -0.0343 | -1.0071 | -5.6597 | 0.9379 | 17.3712 |
| Structural BOS 5/5 (later only) | 10.6383 | 75 | 29 | 46 | 38.6667 | -0.1258 | -1.0165 | -9.4373 | 0.7984 | 12.0822 |

### Directional results

| model | scope | N | net_wins | net_losses | net_win_rate_pct | net_AvgR | net_TotalR | net_PF | net_MaxDD_R |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Current BOS 5/5 (same-bar allowed) | Long | 362 | 153 | 209 | 42.2652 | -0.0792 | -28.6657 | 0.8481 | 36.5857 |
| Current BOS 5/5 (same-bar allowed) | Short | 343 | 131 | 212 | 38.1924 | -0.0594 | -20.3833 | 0.8948 | 30.8245 |
| Structural BOS 2/2 (later only) | Long | 142 | 67 | 75 | 47.1831 | 0.0264 | 3.7503 | 1.0579 | 12.0093 |
| Structural BOS 2/2 (later only) | Short | 113 | 43 | 70 | 38.0531 | 0.0002 | 0.0195 | 1.0003 | 18.1481 |
| Structural BOS 3/3 (later only) | Long | 87 | 41 | 46 | 47.1264 | 0.0003 | 0.0283 | 1.0007 | 8.5940 |
| Structural BOS 3/3 (later only) | Short | 78 | 30 | 48 | 38.4615 | -0.0729 | -5.6880 | 0.8852 | 18.8696 |
| Structural BOS 5/5 (later only) | Long | 36 | 15 | 21 | 41.6667 | -0.0752 | -2.7055 | 0.8693 | 7.6312 |
| Structural BOS 5/5 (later only) | Short | 39 | 14 | 25 | 35.8974 | -0.1726 | -6.7318 | 0.7421 | 10.3378 |

The 2/2 version materially changes the cohort and is marginally positive after costs (AvgR 0.0148, PF 1.0291). That improvement is not broad: 3/3 and 5/5 remain negative, and the effect is not stable across time or outlier removal.

### Time stability

| model | period | N | net_AvgR | net_TotalR | net_PF |
| --- | --- | --- | --- | --- | --- |
| Current BOS 5/5 (same-bar allowed) | 2024 | 296 | -0.1056 | -31.2574 | 0.8144 |
| Current BOS 5/5 (same-bar allowed) | 2025 | 266 | -0.0533 | -14.1825 | 0.8980 |
| Current BOS 5/5 (same-bar allowed) | 2026 | 143 | -0.0252 | -3.6092 | 0.9519 |
| Structural BOS 2/2 (later only) | 2024 | 107 | -0.0964 | -10.3130 | 0.8340 |
| Structural BOS 2/2 (later only) | 2025 | 99 | 0.1481 | 14.6579 | 1.3505 |
| Structural BOS 2/2 (later only) | 2026 | 49 | -0.0117 | -0.5752 | 0.9775 |
| Structural BOS 3/3 (later only) | 2024 | 68 | -0.1045 | -7.1089 | 0.8275 |
| Structural BOS 3/3 (later only) | 2025 | 64 | 0.0385 | 2.4626 | 1.0781 |
| Structural BOS 3/3 (later only) | 2026 | 33 | -0.0307 | -1.0134 | 0.9448 |
| Structural BOS 5/5 (later only) | 2024 | 29 | -0.3256 | -9.4419 | 0.5491 |
| Structural BOS 5/5 (later only) | 2025 | 30 | 0.0968 | 2.9035 | 1.1840 |
| Structural BOS 5/5 (later only) | 2026 | 16 | -0.1812 | -2.8990 | 0.7127 |

| model | period | N | net_AvgR | net_TotalR | net_PF |
| --- | --- | --- | --- | --- | --- |
| Current BOS 5/5 (same-bar allowed) | First 50% | 352 | -0.0741 | -26.0698 | 0.8666 |
| Current BOS 5/5 (same-bar allowed) | Second 50% | 353 | -0.0651 | -22.9793 | 0.8772 |
| Structural BOS 2/2 (later only) | First 50% | 127 | -0.0598 | -7.6000 | 0.8932 |
| Structural BOS 2/2 (later only) | Second 50% | 128 | 0.0888 | 11.3697 | 1.1950 |
| Structural BOS 3/3 (later only) | First 50% | 82 | -0.0514 | -4.2158 | 0.9100 |
| Structural BOS 3/3 (later only) | Second 50% | 83 | -0.0174 | -1.4440 | 0.9674 |
| Structural BOS 5/5 (later only) | First 50% | 37 | -0.0778 | -2.8769 | 0.8752 |
| Structural BOS 5/5 (later only) | Second 50% | 38 | -0.1726 | -6.5604 | 0.7238 |

No structural definition is positive in every year. The 2/2 model is negative in 2024, positive in 2025, and near flat/negative in 2026; its first half is negative and second half positive. The 3/3 and 5/5 variants remain negative overall and do not establish a broad stable structural effect.

### Outlier robustness

| model | scenario | N | net_AvgR | net_TotalR | net_PF |
| --- | --- | --- | --- | --- | --- |
| Current BOS 5/5 (same-bar allowed) | Full | 705 | -0.0696 | -49.0491 | 0.8718 |
| Current BOS 5/5 (same-bar allowed) | Remove best trade | 704 | -0.0725 | -51.0432 | 0.8666 |
| Current BOS 5/5 (same-bar allowed) | Remove top 1% winners | 697 | -0.0932 | -64.9734 | 0.8302 |
| Structural BOS 2/2 (later only) | Full | 255 | 0.0148 | 3.7697 | 1.0291 |
| Structural BOS 2/2 (later only) | Remove best trade | 254 | 0.0070 | 1.7777 | 1.0137 |
| Structural BOS 2/2 (later only) | Remove top 1% winners | 252 | -0.0087 | -2.1975 | 0.9830 |
| Structural BOS 3/3 (later only) | Full | 165 | -0.0343 | -5.6597 | 0.9379 |
| Structural BOS 3/3 (later only) | Remove best trade | 164 | -0.0466 | -7.6491 | 0.9161 |
| Structural BOS 3/3 (later only) | Remove top 1% winners | 163 | -0.0591 | -9.6339 | 0.8943 |
| Structural BOS 5/5 (later only) | Full | 75 | -0.1258 | -9.4373 | 0.7984 |
| Structural BOS 5/5 (later only) | Remove best trade | 74 | -0.1544 | -11.4267 | 0.7559 |
| Structural BOS 5/5 (later only) | Remove top 1% winners | 74 | -0.1544 | -11.4267 | 0.7559 |

The marginally positive 2/2 result survives removal of its single best trade but turns negative after removing the top 1% of winners (AvgR -0.0087, PF 0.9830). The 3/3 and 5/5 variants are already negative and worsen under both removals.

## 8. Causality and lookahead checks

- Metadata-rich 5/5 replay matched the frozen Phase 3 event on every processed bar.
- Every pivot confirmation is origin bar + right bars.
- Every audited current/diagnostic break used a pivot confirmed before the break bar.
- No current BOS reference was already crossed on the prior bar (0/705).
- Counterfactual BOS is strictly after Setup; retest is strictly after BOS; confirmation is strictly after retest.
- Automated synthetic tests prove break-before-pivot ordering and reject same-bar counterfactual BOS.

**LOOKAHEAD CHECK: PASS.**

## 9. Deterministic case studies

The audit contains 50 deterministic, chronologically spread cases: 10 same-bar winners, 10 same-bar losers, 10 delayed BOS, 10 without a same-bar 3/3 break, and 10 with a same-bar 3/3 break. Structured records are in `bos_case_studies.csv`; five chart sheets are under `case_study_charts/` and embedded in the workbook.

## 10. Required questions

1. **What exactly is the current BOS?** A close beyond the most recent confirmed, unused 5/5 pivot in the setup direction. Both Phase 3 BOS and CHoCH break events qualify for the funnel's `BOS` label.
2. **Why are 664/705 same-bar?** Phase 5 uses that directional break to create Setup, then Phase 12's separate same-bar `if` consumes the identical still-true event as BOS.
3. **Does it normally break an actual confirmed swing?** Yes under its own 5/5 definition: 705/705. It also coincides with 2/2 in 533 cases and 3/3 in 615.
4. **Is it substantially redundant with Setup?** Yes on realized trades (94.18% immediate and direct Boolean reuse), though only 67.87% of all canonical setups have immediate BOS.
5. **Are Setup, BOS, Retest, Confirm separate causal events?** Retest and Confirm are sequential later bars. Setup and BOS are usually one event; Confirm and Entry are intentionally one event.
6. **Does causal later-only structural BOS materially change trades?** Yes: retention falls to 36.17%, 23.40%, and 10.64% for 2/2, 3/3, and 5/5.
7. **Does it improve expectancy after costs?** The 2/2 model is marginally positive (AvgR 0.0148, PF 1.0291); 3/3 and 5/5 remain negative.
8. **Is improvement stable across definitions?** No. Results degrade from near-flat 2/2 to negative 3/3 and more negative 5/5.
9. **Is improvement stable across time?** No. No alternative is positive in every year or both chronological halves.
10. **Is improvement dependent on a few winners?** The 2/2 positive result survives removal of the best trade, but removing the top 1% of winners makes it negative (AvgR -0.0087, PF 0.9830); therefore the positive conclusion is outlier-sensitive.

## 11. Recommendation

Do not implement a new structural-BOS rule from this audit. First decide the semantic design question explicitly: whether Setup may be triggered by the same break that the next funnel stage calls BOS, or whether BOS is intended to be an independent later confirmation. If independence is required, the preregistered later-only replacements tested here do not supply a robust profitable solution and should remain research-only.

Pine modified: **NO**. Frozen baseline modified: **NO**. No unseen/OOS data was accessed in this semantic audit.
