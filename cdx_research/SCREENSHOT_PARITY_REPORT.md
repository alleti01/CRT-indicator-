# Screenshot parity report

**No exact-bar or ±1-bar score is valid yet.**

Research NQ 1m (`load_market_1m_lw`) ends **2026-09-02 10:48 America/Chicago**.  
Every labeled CDX signal is **2026-09-06 through 2026-09-21**.

| Confidence | N | Matched OHLCV | Exact | ±1 | Missed | Extra | Wrong dir |
|---|---|---|---|---|---|---|---|
| HIGH | 0 | 0 | — | — | — | — | — |
| HIGH+MEDIUM | 10 | 0 | 0 | 0 | 10 | n/a | 0 |
| ALL | 36 | 0 | 0 | 0 | 36 | n/a | 0 |

Exact recall / precision / F1: **not computed** (denominator would be fake).

RTH vs overnight among labels (session from clock, not bars):

- MEDIUM: 3 RTH (s06, s07×2), 7 overnight/globex
- ALL: mixed; CDX is not RTH-only

LOW labels (26) are excluded from any future exact-bar score.

s03/s04 were the same frame; only s03 was kept.

See `parity/screenshot_parity.csv`.
