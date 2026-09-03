# Lookahead Audit

## Rule
A completed 15m candle cannot use internal 1m bars retroactively.
`actionable_timestamp = marker_bar_timestamp + 15 minutes`.
All 1m confirmation scans begin at the first eligible 1m bar on or after `actionable_timestamp`.

## Checks
- first_eligible_1m <= actionable_timestamp for all signals: **PASS**
- negative 1m entry delays: **0** (must be 0)
- 1m_timestamp >= 15m_signal_available_timestamp enforced in confirm.py scan windows

## Result: **PASS**
