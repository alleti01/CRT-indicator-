# CDX stop × higher-timeframe filter replay, Sep 22 – Oct 2 2026 (eval sim from Sep 8)

Research only. Production was not changed. Script: `forward_rehearsal/research/htf_stop_replay.py`.

## Data

- 104 webhook signals from `phase74/logs/signals.jsonl`, Sep 22 (first CDX-only day) to Oct 2 10:27 ET, manual reentries dropped, same-direction duplicates within 60 s collapsed.
- **Real 1-minute OHLC from `phase74/logs/bars.csv`** (Sep 9 – Oct 2, pushed from Windows). The few minutes before Sep 9 05:48 UTC fall back to closes from `decisions.jsonl`.
- 15m / 1H bias from `phase74/quality/htf_bias.py`, the same code the live shadow log uses, on bars closed before the signal minute.

## Update: real bars (this report)

The first version of this report used bars rebuilt from closes, with no wicks. With real highs and lows:

- The 15m split held: agrees 22 signals, median 4h move **130 points**; neutral 13, 44 points; against 69, 17 points.
- The fixed 14.25 stop got worse. Even with 15m agreeing it is negative at 2R (−1.5R over 21 trades); 10 of its 14 stop-outs on those signals then reached +2R.
- Structural stops got wider (median 20 points for 5 bars, 29 for 10 bars) and stayed positive with 15m agreeing.
- The 1.5 × ATR stop went from worst to best. A ranking that flips this much between data sources is a warning that the stop choice is not settled.

## Rules

Entry at the webhook price. One position at a time. Stop before target inside a bar. 1.0 point round-trip cost. Close after 4 hours if neither is hit.

| Stop | Definition | Median distance |
|---|---|---|
| fixed_14.25 | 14.25 points (old live stop) | 14.25 |
| struct5 | beyond the extreme of the last 5 closed 3m bars + 0.05 ATR | 20.0 |
| struct10 | same, last 10 closed 3m bars | 29.0 |
| atr1.5 | 1.5 × ATR(14) on 3m | 28.8 |

## 15m structure at the signal

| 15m vs. signal | Signals | Median best move in 4h |
|---|---|---|
| agrees | 22 | **130 points** |
| neutral | 13 | 44 points |
| against | 69 | 17 points |

"Agrees" had a high median move on **every** day in the sample (46–169 points). "Against" is dominated by Sep 28 (53 of 69, a burst of repeated alerts); outside Sep 28 it is mixed (Oct 1: median 163 points).

## Scorecard, 2R target (real bars)

| Stop | Filter | Trades | Win | Avg R | Total R | PF | Max DD R | Sep 22–26 | Sep 28–Oct 2 |
|---|---|---|---|---|---|---|---|---|---|
| fixed_14.25 | none | 72 | 26% | −0.28 | −20.1 | 0.65 | 24.6 | −9.2 | −10.9 |
| fixed_14.25 | 15m agrees | 21 | 33% | −0.07 | −1.5 | 0.90 | 7.5 | +2.4 | −3.8 |
| struct5 | 15m agrees | 19 | 58% | +0.69 | +13.1 | 2.87 | 2.4 | +3.9 | +9.3 |
| struct10 | 15m agrees | 18 | 72% | +0.75 | +13.6 | 4.25 | 2.1 | +5.0 | +8.6 |
| **atr1.5** | **15m agrees** | **19** | **68%** | **+0.93** | **+17.7** | **3.84** | **3.1** | **+7.0** | **+10.7** |
| atr1.5 | none | 52 | 38% | +0.08 | +4.0 | 1.12 | 14.2 | +5.8 | −1.8 |

## 50k eval simulation (real bars)

$3,000 target, $2,000 trailing drawdown, bot day rules (1 winner / 2 losers / −$400), $1,000 per-trade cap, 2R target. Eval started on each session from Sep 8; starts with fewer than 5 sessions of data left are dropped unless they finished. Sep 8–21 signals are from the Phase72A indicator, not CDX.

| Stop | Filter | Risk/trade | Starts | Passed ≤5 days | Passed | Blown | Median days |
|---|---|---|---|---|---|---|---|
| fixed_14.25 | none | $600 | 15 | 1 | 5 | 5 | 5 |
| struct5 | 15m agrees | $600 | 15 | 4 | 14 | 0 | 7 |
| **atr1.5** | **15m agrees** | **$600** | **15** | **5** | **15** | **0** | **6** |
| atr1.5 | 15m agrees | $400 | 14 | 0 | 10 | 1 | 9 |

## Findings

1. **Only take CDX signals when the 15m structure agrees.** It is the one filter that is positive for every stop type and in both halves of the sample.
2. **The fixed 14.25-point stop is the problem on those same signals.** Where the 15m agrees, it is hit on 14, and 10 of those 14 then reach +2R inside 4 hours. Structural or 1.5 × ATR stops (20–30 points median) turn −1.5R into +13R to +18R.
3. **Adding "1H not against" does not help** beyond 15m agreeing: fewer trades, similar total R.
4. **The live rule "skip only when both timeframes disagree" is too loose.** It is weaker than "15m agrees" for every stop and still loses with the fixed stop.
5. **Size by dollar risk, not contracts.** With 15m agreeing and a $600 risk per trade, the eval passed from every start date in the sample, a third of them within 5 sessions, with none blown.

## Limits

- About 20 filtered trades over 2 weeks. A promising result, not a proven edge.
- One market stretch (Sep 8 – Oct 2). Different conditions may rank the stops differently.
- 4-hour hold and one-position rule are simplifications of the live management (trail, day halts, session pauses).
