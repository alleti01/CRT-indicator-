# Phase71 Frozen Spec
Signal hash: `0da41f282174679f`
Trader hash: `b6adfc04e8885a3d`

## Rules
- Entry: signal bar T close → next 1M open T+1
- Stop: 1.0 ATR initial
- Target: +2.5R
- T5: at 15 completed minutes, if running MFE < +1.0R → exit at market (once)
- Max hold: 60 minutes
- Collision: STOP_FIRST (stop/target before T5)

## T5 timing
Entry at bar `ei` open. First management bar `ei+1` = minute 1.
First T5 evaluation at bar `ei+15` when `minutes_in_trade >= 15`.
Example: entry 09:31 → T5 check at 09:46 bar.

## MFE
LONG: (max high since entry) - entry) / risk
SHORT: (entry - min low since entry) / risk
MFE_R >= 1.0 → PASS (hold); MFE_R < 1.0 → EXIT_TIME_PROGRESS