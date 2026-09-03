# Phase58 Build Report

## Architecture
- Sequential bar-close state machine (WATCH -> ARMED -> REACTION -> TAKE -> IN_TRADE -> COOLDOWN)
- Precomputed immutable arrays (hi/lo/cl/op/atr/swings/HTF) — extracted once
- Context: 1M swing progression + momentum + 5M/15M direction
- Location: swing proximity + pullback depth + range position (all ATR-normalized)
- Reaction: 6 causal evidence components (failed extension, momentum loss, reclaim, directional response, micro shift, rejection)
- Evidence scoring: fixed integer weights, take threshold = 4
- Anti-chase: continuous deterioration measurement, max 1.5 ATR
- Entry: next-bar open after signal
- Stop/target: 0.75 ATR / 2.5R / 60m hold

## Performance
- Engine runtime: ~35 seconds on 3M bars
- Total runtime (with evaluation): ~1.5 minutes
- 223k trades generated across full history

## Instrument Adapter
- Normalized: ATR-relative distances, percentage pullback depth
- NQ defaults via InstrumentSpec dataclass
- Extensible to any instrument with tick_size, point_value, session, cost

## S54 Hash: bccf4277f3d44d13 (unchanged)
