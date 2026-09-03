# Pine Validation Checklist

## Setup
- [ ] Chart: NQ continuous, **15-minute**, timezone **America/Chicago**
- [ ] Add `NQ_15M_COMBINED_INDICATOR.pine`
- [ ] **Show Debug = OFF**
- [ ] **Show Exit Markers = OFF** (default)

## Marker meanings
- `L` = Phase 31 continuation LONG (BOS_RETEST fill)
- `S` = Phase 31 continuation SHORT
- `RL` = Phase 33 reversal LONG (A_MID_4 + RECLAIM_RETEST fill)
- `RS` = Phase 33 reversal SHORT

## Parity windows
Validate each row in `parity_windows.csv` against chart markers and levels.

## Alerts
Test: CONTINUATION LONG/SHORT, REVERSAL LONG/SHORT, PHASE31/33 STOP/TARGET/TIME

## Non-repaint
Reload chart — historical markers must not move or disappear.

## Known feed differences
Python uses stitched CSV 5m→15m aggregation. TradingView continuous contract may differ slightly in bar OHLC.
