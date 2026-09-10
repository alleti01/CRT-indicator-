# Signal Validation — 2026-09-08

Gates: pass_chase=True, pass_late=True

## Summary

- **Signals analyzed:** 26
- **Would enter (simulated):** 21
- **Skipped by gates:** 5
- **Winners (gross R > 0):** 13
- **Losers:** 8
- **Entered in CHOP regime:** 6
- **Total gross R:** +24.50
- **Avg gross R:** +1.17

## Per-signal

| ET | Event | Observed | Gate | Chase ATR | Regime | Exit | Gross R | Valid? |
|----|-------|----------|------|-----------|--------|------|---------|--------|
| 21:22:00 | SIGNAL_LONG | PASS_DATA_UNHEALTHY | PASS_DATA_UNHEALTHY | +7.75 | UNKNOWN |  |  | SKIP |
| 21:49:01 | SIGNAL_LONG | WOULD_ENTER | PASS_STALE | +0.00 | UNKNOWN |  |  | SKIP |
| 22:10:59 | SIGNAL_LONG | WOULD_ENTER | TAKE_LONG | +0.00 | UNKNOWN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 22:28:01 | SIGNAL_LONG | WOULD_ENTER | PASS_STALE | +0.00 | UNCERTAIN |  |  | SKIP |
| 00:07:00 | SIGNAL_LONG | WOULD_ENTER | TAKE_LONG | +0.00 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 01:28:00 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 02:55:08 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | CHOP | WOULD_EXIT_STOP | -1.00 | LOSS |
| 03:04:02 | SIGNAL_LONG | WOULD_ENTER | TAKE_LONG | +0.00 | CHOP | WOULD_EXIT_TARGET | +2.50 | WIN |
| 04:31:01 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | CHOP | WOULD_EXIT_STOP | -1.00 | LOSS |
| 04:52:00 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | UNCERTAIN | WOULD_EXIT_STOP | -1.00 | LOSS |
| 05:25:04 | SIGNAL_LONG | WOULD_ENTER | TAKE_LONG | +0.00 | UNCERTAIN | WOULD_EXIT_STOP | -1.00 | LOSS |
| 06:46:05 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 07:16:59 | SIGNAL_LONG | WOULD_ENTER | TAKE_LONG | -0.55 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 07:40:01 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | CHOP | WOULD_EXIT_TARGET | +2.50 | WIN |
| 08:28:59 | SIGNAL_LONG | WOULD_ENTER | TAKE_LONG | +0.68 | UNCERTAIN | WOULD_EXIT_STOP | -1.00 | LOSS |
| 09:51:00 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 10:31:00 | SIGNAL_SHORT | PASS_DATA_UNHEALTHY | PASS_DATA_UNHEALTHY | +0.00 | UNCERTAIN |  |  | SKIP |
| 12:08:58 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.66 | CHOP | WOULD_EXIT_TARGET | +2.50 | WIN |
| 12:29:01 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 12:48:00 | SIGNAL_LONG | WOULD_ENTER | TAKE_LONG | +0.00 | CHOP | WOULD_EXIT_STOP | -1.00 | LOSS |
| 14:32:00 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | UNCERTAIN | WOULD_EXIT_STOP | -1.00 | LOSS |
| 14:58:58 | SIGNAL_LONG | WOULD_ENTER | TAKE_LONG | -0.23 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 15:18:58 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.73 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |
| 16:16:58 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.03 | UNCERTAIN | WOULD_EXIT_STOP | -1.00 | LOSS |
| 18:39:12 | SIGNAL_LONG | PASS_DATA_UNHEALTHY | PASS_DATA_UNHEALTHY | +0.00 | CHOP |  |  | SKIP |
| 19:26:01 | SIGNAL_SHORT | WOULD_ENTER | TAKE_SHORT | +0.00 | UNCERTAIN | WOULD_EXIT_TARGET | +2.50 | WIN |

## Notes

- Outcomes use M0 management (1.0 ATR stop, 2.5R target, 60m hold) on reconstructed 1m bars.
- Bars from `decisions.csv` WATCH rows when `--bars-csv` is not supplied (close-derived OHLC).
- Regime labels are observational (Phase75); CHOP does not block entry in this report.
- CSV: `forward_rehearsal/reports/2026-09-08_signal_validation.csv`
