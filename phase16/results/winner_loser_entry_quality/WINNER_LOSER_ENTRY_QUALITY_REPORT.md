# Winner vs Loser Entry-Quality Forensics

## Scope and guardrails

This is development-window forensic discovery only: 10,164 five-minute bars from 2026-06-29 through 2026-08-18 in America/Chicago, with warm-up history beginning 2026-05-31 19:00 CT. The unseen OOS dataset was not accessed. Pine, the frozen Python engines, entries, stops, targets, filters, and the $14.50 round-turn cost assumption were not modified.

All explanatory variables were available by the entry-bar close. Outcome, MFE, MAE, exits, and net/gross R were labels only. Quantile and median splits are descriptive devices, not proposed trading thresholds.

## CURRENT

- N: 42
- Wins: 17
- Losses: 25
- Win rate: 40.48%
- AvgR: -0.00846
- TotalR: -0.35512
- PF: 0.98369
- MaxDD: 8.37128R

## Top 10 pre-entry features separating winners and losers

| Rank | Feature | Relationship | Cohen d | Winner median | Loser median | LOO stability | Outlier check | Market rationale |
|---:|---|---|---:|---:|---:|---|---|---|
| 1 | Entry ATR (points) | Higher among winners | 0.711 | 35.065 | 27.835 | STABLE | ROBUST TO LISTED REMOVALS | Volatility state changes the noise-to-signal ratio and the dollar cost expressed in R. |
| 2 | Retest range / ATR | Higher among winners | 0.569 | 1.068 | 0.891 | STABLE | ROBUST TO LISTED REMOVALS | Retest depth, rejection, and delay proxy acceptance versus erosion of the newly broken structure. |
| 3 | Bars retest to confirmation | Higher mean among winners; medians equal | 0.552 | 1.000 | 1.000 | STABLE | ROBUST TO LISTED REMOVALS | Retest depth, rejection, and delay proxy acceptance versus erosion of the newly broken structure. |
| 4 | Setup lower wick / range | Lower among winners | -0.523 | 0.132 | 0.200 | STABLE | ROBUST TO LISTED REMOVALS | The frozen setup components summarize the upstream liquidity, structure, bias, displacement, and session context. |
| 5 | BOS close displacement (points) | Higher among winners | 0.486 | 34.250 | 22.500 | PARTIALLY STABLE | ROBUST TO LISTED REMOVALS | A decisive, well-participated structure break may be less prone to immediate failure than a marginal break. |
| 6 | Retest body / ATR | Higher among winners | 0.456 | 0.422 | 0.234 | STABLE | ROBUST TO LISTED REMOVALS | Retest depth, rejection, and delay proxy acceptance versus erosion of the newly broken structure. |
| 7 | BOS lower wick / range | Lower among winners | -0.437 | 0.132 | 0.194 | STABLE | ROBUST TO LISTED REMOVALS | A decisive, well-participated structure break may be less prone to immediate failure than a marginal break. |
| 8 | Setup session component | Higher among winners | 0.426 | 10.000 | 0.000 | STABLE | ROBUST TO LISTED REMOVALS | The frozen setup components summarize the upstream liquidity, structure, bias, displacement, and session context. |
| 9 | Retest close beyond BOS / ATR | Higher among winners | 0.414 | 0.380 | 0.240 | PARTIALLY STABLE | ROBUST TO LISTED REMOVALS | Retest depth, rejection, and delay proxy acceptance versus erosion of the newly broken structure. |
| 10 | BOS volume / prior-20 mean | Higher among winners | 0.368 | 1.647 | 1.297 | PARTIALLY STABLE | SENSITIVE TO OUTLIER REMOVAL | A decisive, well-participated structure break may be less prone to immediate failure than a marginal break. |

## Top loser characteristics

1. **Overnight or premarket** — 17/25 losses (68.0%), 7/17 winners; conditional AvgR -0.153, PF 0.748. Definition: Entry outside frozen 09:30-16:00 preferred session.
2. **Weak confirmation body** — 10/25 losses (40.0%), 1/17 winners; conditional AvgR -0.709, PF 0.063. Definition: Bottom quartile confirmation body / ATR.
3. **Weak directional close location** — 9/25 losses (36.0%), 2/17 winners; conditional AvgR -0.499, PF 0.352. Definition: Bottom quartile confirmation close location in trade direction.
4. **Low relative BOS volume** — 7/25 losses (28.0%), 4/17 winners; conditional AvgR -0.340, PF 0.364. Definition: Bottom quartile causal BOS relative volume.
5. **Weak BOS displacement** — 7/25 losses (28.0%), 4/17 winners; conditional AvgR -0.080, PF 0.835. Definition: Bottom quartile BOS displacement / ATR.

## Top winner characteristics

1. **Strong BOS displacement** — 7/17 winners (41.2%), 4/25 losses; conditional AvgR 0.630, PF 3.338. Definition: Top quartile BOS displacement / ATR.
2. **Longer confirmation delay (counterintuitive)** — 7/17 winners (41.2%), 4/25 losses; conditional AvgR 0.485, PF 2.494. Definition: Top quartile retest-to-confirm delay.
3. **Core session** — 10/17 winners (58.8%), 8/25 losses; conditional AvgR 0.184, PF 1.459. Definition: Entry in frozen 09:30-16:00 preferred session.
4. **High relative BOS volume** — 6/17 winners (35.3%), 5/25 losses; conditional AvgR 0.441, PF 2.079. Definition: Top quartile causal BOS relative volume.
5. **Shallow retest penetration** — 5/17 winners (29.4%), 6/25 losses; conditional AvgR 0.294, PF 1.577. Definition: Bottom quartile max penetration through BOS / ATR.

## Best apparent two-feature interactions

1. **High relative volume + strong BOS** — Both-cell N 15, WR 60.0%, AvgR 0.562, PF 2.554; AvgR difference versus Neither 0.832. Exploratory only.
2. **Core session + strong confirmation** — Both-cell N 10, WR 60.0%, AvgR 0.221, PF 1.621; AvgR difference versus Neither 0.224. Exploratory only.
3. **Strong BOS + shallow retest** — Both-cell N 9, WR 55.6%, AvgR 0.219, PF 1.533; AvgR difference versus Neither 0.556. Exploratory only.
4. **Strong BOS + strong confirmation** — Both-cell N 7, WR 57.1%, AvgR 0.088, PF 1.203; AvgR difference versus Neither 0.523. Exploratory only.
5. **HTF aligned + strong BOS** — Both-cell N 8, WR 50.0%, AvgR 0.041, PF 1.098; AvgR difference versus Neither 0.117. Exploratory only.

## Distribution and stability interpretation

- BOS close displacement / ATR: NON-MONOTONIC; bucket-order/AvgR Spearman 0.400; smallest bucket N 10.
- Confirmation body / ATR: NON-MONOTONIC; bucket-order/AvgR Spearman -0.400; smallest bucket N 10.
- Max pre-accept penetration / ATR: NON-MONOTONIC; bucket-order/AvgR Spearman -0.200; smallest bucket N 10.
- Entry ATR percentile vs prior 100 bars: NON-MONOTONIC; bucket-order/AvgR Spearman 0.200; smallest bucket N 7.
- Bars BOS to retest: NON-MONOTONIC; bucket-order/AvgR Spearman -0.200; smallest bucket N 2.
- Bars retest to confirmation: NON-MONOTONIC; bucket-order/AvgR Spearman 0.500; smallest bucket N 3.
- Original setup score: NON-MONOTONIC; bucket-order/AvgR Spearman 0.400; smallest bucket N 2.

## Is there evidence that entry quality can be improved?

**WEAK.** The sample contains observed pre-entry separation, but N=42 is too small and all evidence comes from the development window. Any promising relationship must be defined prospectively and tested without revisiting the unseen OOS sample.

## Most promising three hypotheses for future preregistered testing

- **H1 — BOS impulse plus participation:** entries with jointly stronger causal BOS displacement and relative volume have better expectancy than valid breaks lacking both characteristics.
- **H2 — Retest acceptance quality:** entries whose accepted retest candle shows stronger directional body/range expansion and closes farther back onto the intended side of stored BOS have better expectancy than weaker accepted retests.
- **H3 — Volatility-and-session context:** valid entries in a higher, already-known ATR state and the frozen core session have better expectancy than otherwise-valid entries in quieter/off-session conditions.

No numeric cutoff is recommended here. Any later test should preregister structural definitions or fixed non-profit-derived splits before opening unseen data.

## Feature definitions and leakage controls

- BOS displacement is the direction-signed BOS close change from the prior bar close; close-beyond-structure is reported separately against the stored BOS level.
- Relative volume uses the BOS bar volume divided by the mean of the prior 20 completed bars; the BOS bar is excluded from the denominator.
- Entry ATR percentile compares the known entry-bar ATR with up to 100 completed prior bars.
- Session high/low are cumulative within the CME session and include only bars through the entry bar.
- Retest penetration is measured from BOS+1 through the accepted retest; confirmation is strictly later than retest.
- Setup and BOS occurred on the same bar for 41 of 42 trades. Their candle-shape fields are therefore usually duplicate observations, not independent evidence; raw upper/lower wick effects also require direction-aware interpretation.
- The apparent benefit of a longer confirmation delay is sparse: 31 trades confirmed after one bar, eight after two bars, and three after three bars. It is not a monotonic threshold finding.
- Cohen d is descriptive. LOO stability is STABLE when all leave-one-out signs agree and the smallest absolute effect is at least 75% of the full effect; PARTIALLY STABLE uses at least 90% sign agreement and 50% effect retention.
- Outlier checks separately remove the best trade, worst trade, top two winners, and top two losers.
