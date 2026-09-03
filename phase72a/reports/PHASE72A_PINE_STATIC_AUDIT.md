# Phase72A Pine Static Audit

- **Lines:** 1501
- **lookahead_on active:** False (must be False)
- **request.security calls:** 9
- **DEBUG_MANUAL_SIGNAL default false:** True

## request.security inventory

| ID | TF | Lookahead | Purpose |
|----|-----|-----------|---------|
| 1 | 5 | off | completed OHLC [1] |
| 2 | 15 | off | completed OHLC [1] |
| 3 | 5 | off | time[1] |
| 4 | 15 | off | time[1] |
| 5 | 5 | off | pivothigh/pivotlow |
| 6 | 15 | off | high[4], low[4], close[12] |

## Dangerous patterns checked

- var initialization: standard Pine persistence
- na propagation: f_atrUse fallback
- timeframe: TZ_WARN if not 1M
- No lookahead_on for HTF OHLC

**PASS:** True