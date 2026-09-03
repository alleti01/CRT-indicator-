# Profile Construction

Session: prior RTH only (`0930-1600` America/Chicago).
Bin width: **0.25 points** (NQ minimum tick).
Value area: **70%** expanded from POC using adjacent-bin volume tie-break.

## Approximation note
Tick-level volume-at-price is unavailable in stored 5m OHLCV.
Each bar's volume is distributed uniformly across tick bins touched by [low, high].
POC/VAH/VAL are research approximations, not exchange-confirmed TPO profiles.

Profiles lock after prior RTH completes and become available at the next RTH open.
