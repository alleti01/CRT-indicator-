# Data audit

Bars: `phase74/logs/bars.csv` from the NinjaTrader 1-minute bridge. No alternate feed.

Signals: `phase74/logs/signals.csv`. The `timeframe` column is `1m` because the bot rejects any other value. The CDX chart that produced the alerts is 3-minute. Structural stops and ATR14 use completed 3-minute bars grouped on 180-second Unix buckets, using only bars whose close time is at or before the fill.

Path, stops, MFE, MAE, and ratchet use 1-minute bars after the fill.

Fills: `phase85/logs/audit.jsonl`, reconciled to `forward_rehearsal/reports/WEEK_TRADES_2026-09-22.md`.

15 live attempts. Tuesday 10:52 AM short is an execution failure and is excluded. Tuesday 3:12 PM and Wednesday 10:56 AM have no exit fill; their management paths are hypothetical. Friday 12:24 PM long has no exit fill; the 3:00 PM bar close 30868.50 is an estimate, about +9.75 points. The scorecard uses the 11 trades with both prices.

Checkpoint convention: an early-failure or no-progress exit is the close of the 1-minute bar that completes the 3rd or 6th 3-minute bar after the fill. The stop active at the start of that minute is tested first. A ratchet computed from that minute's MFE becomes active on the next minute.

Runner after +2R: `phase74/quality/trail.py`, `TrailOverlay._cap_or_reversal`. Cap at 3R of the frozen initial R. Trail 10 points behind the extreme. The bar that sets a new extreme does not stop itself. Systems B and C arm that same trail once MFE reaches +1R, because that is when the live runner arms. Systems F through I arm it only after +2R, per this phase.

Max hold: the live rule exits at the close once 60 minutes have passed and the close is no longer beyond the entry. A close that is still in profit does not time-exit. Nothing still open at the last bar is counted as realized profit. In this sample every complete-trade replay exited, so open marks are zero.
