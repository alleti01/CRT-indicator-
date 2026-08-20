# Retest-gated forensic trace

Window: 2026-06-29 00:00:00-05:00 through 2026-08-19 00:00:00-05:00 (end exclusive)

## Exact frozen definitions

- BOS level: the prior active confirmed structural swing that the Phase 3 close broke; current active swing is only the existing fallback when the prior value is unavailable.
- Retest tolerance: current-bar ATR(14) × 0.1.
- Short retest touch: after the BOS bar, `high >= BOS level - tolerance`. Wick penetration counts.
- Short retest invalidation: `close > BOS level + tolerance`. The bar is rejected before touch acceptance when both are true.
- Retest expiry: more than 8 bars after BOS; minimum delay is one full bar.
- Short confirmation: after the retest bar, `close < open AND close < BOS level`.
- Short confirmation invalidation: `close > BOS level + tolerance`.
- Confirmation expiry: more than 8 bars after retest; minimum delay is one full bar.
- Opposite bullish BOS cancels an active short in WAIT_BOS, WAIT_RETEST, or WAIT_CONFIRM in the current live gate.

## Short funnel

- Setup: 120
- Variant-C qualified: 70
- Candidate accepted: 60
- BOS: 44
- Retest touched: 40
- Retest accepted: 26
- Confirm candidate: 26
- Confirm accepted: 21
- Entry: 21

## Long funnel

- Setup: 136
- Variant-C qualified: 90
- Candidate accepted: 81
- BOS: 60
- Retest touched: 52
- Retest accepted: 34
- Confirm candidate: 34
- Confirm accepted: 21
- Entry: 21

## Long first-death rejection counts

- regime restriction: 43 (31.62% of raw long setups)
- retest touched but rejected: 17 (12.50% of raw long setups)
- opposite BOS invalidation: 16 (11.76% of raw long setups)
- confirmation condition rejected: 12 (8.82% of raw long setups)
- setup rejected: 9 (6.62% of raw long setups)
- retest expired: 8 (5.88% of raw long setups)
- BOS expired: 7 (5.15% of raw long setups)
- session restriction: 3 (2.21% of raw long setups)
- confirmation never occurred: 0 (0.00% of raw long setups)
- invalid risk: 0 (0.00% of raw long setups)
- no matching BOS: 0 (0.00% of raw long setups)
- other: 0 (0.00% of raw long setups)
- retest never touched: 0 (0.00% of raw long setups)

## Short first-death rejection counts

- regime restriction: 49 (40.83% of raw short setups)
- opposite BOS invalidation: 14 (11.67% of raw short setups)
- retest touched but rejected: 13 (10.83% of raw short setups)
- setup rejected: 10 (8.33% of raw short setups)
- confirmation condition rejected: 5 (4.17% of raw short setups)
- retest expired: 4 (3.33% of raw short setups)
- BOS expired: 3 (2.50% of raw short setups)
- session restriction: 1 (0.83% of raw short setups)
- confirmation never occurred: 0 (0.00% of raw short setups)
- invalid risk: 0 (0.00% of raw short setups)
- no matching BOS: 0 (0.00% of raw short setups)
- other: 0 (0.00% of raw short setups)
- retest never touched: 0 (0.00% of raw short setups)

## Short retest Boolean evaluations

- touch_condition: true 40, false 51
- invalid_condition: true 14, false 77
- opposite_bos: true 1, false 90

## Short confirmation Boolean evaluations

- directional_candle: true 21, false 14
- close_beyond_bos_level: true 28, false 7
- confirmed: true 21, false 14
- invalid_condition: true 5, false 30
- opposite_bos: true 0, false 35

## Near-miss definition

Near misses are diagnostic only: no-entry shorts that passed BOS, came within 1 ATR of the stored level, and then achieved at least 1 ATR downward MFE within the next expiry-length window after the first bearish post-retest/closest-level proxy bar. Future excursion is never used by qualification.

Near-miss rows: 12

Top five by diagnostic MFE/ATR:

- 2026-08-14 08:05:00-05:00: BOS 29890.75, closest 13.50 points (0.606 ATR), retest accepted=False, confirmation passed=False, MFE=103.75 (3.764 ATR), MAE=42.50 (1.542 ATR), reason=Retest wick touched band, but close invalidated beyond 29892.97771923796
- 2026-08-18 15:45:00-05:00: BOS 29241.50, closest 1.50 points (0.082 ATR), retest accepted=True, confirmation passed=False, MFE=56.00 (3.042 ATR), MAE=18.75 (1.019 ATR), reason=Confirmation close invalidated beyond 29243.41087031912
- 2026-07-22 14:25:00-05:00: BOS 28890.00, closest 15.75 points (0.577 ATR), retest accepted=False, confirmation passed=False, MFE=84.75 (3.003 ATR), MAE=56.25 (1.993 ATR), reason=Retest wick touched band, but close invalidated beyond 28892.729173183485
- 2026-08-11 00:25:00-05:00: BOS 29497.25, closest 3.00 points (0.233 ATR), retest accepted=False, confirmation passed=False, MFE=37.50 (2.872 ATR), MAE=12.25 (0.938 ATR), reason=Retest wick touched band, but close invalidated beyond 29498.538532983675
- 2026-07-16 13:50:00-05:00: BOS 28901.25, closest 4.50 points (0.112 ATR), retest accepted=True, confirmation passed=False, MFE=106.25 (2.530 ATR), MAE=56.00 (1.333 ATR), reason=Confirmation close invalidated beyond 28905.2771214044

## Symmetry audit

The direction branches are exact mirrors: low/upper-band/bullish/above-level for longs versus high/lower-band/bearish/below-level for shorts. No direction-specific score, expiry, or state-order difference is introduced by this tracer.

## Final finding

ROOT CAUSE OF MISSING RETEST ENTRIES: The live gate is behaving exactly as coded. A short touch is terminally rejected before acceptance when that same bar closes above BOS + 0.10×current-bar ATR; after an accepted touch, a close above the same upper band terminates WAIT_CONFIRM before a later bearish rejection can qualify. These resets explain the visually strong later selloffs with no SHORT marker. They are frozen rule effects, not an ordering/state defect.

MOST IMPORTANT BOTTLENECK: Retest stage. Of 44 short BOS candidates, 26 reached accepted retest; 13 touched but closed beyond the upper band, 4 expired, and 1 was cancelled by an opposite BOS while waiting for retest.

RETEST RULE TOO STRICT? INCONCLUSIVE

CONFIRM RULE TOO STRICT? INCONCLUSIVE

STATE-MACHINE BUG? NO

LONG/SHORT ASYMMETRY? NO

STRATEGY CHANGE RECOMMENDED? NO
