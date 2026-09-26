# CDX recovery data (isolated)

This folder is **not** the Phase58J / `load_market_1m_lw` series.

| File | Source label | May merge into phase58j? |
|---|---|---|
| `nq_continuous_1m_lw_extension_sep2026.csv` | DATABENTO `NQ.v.0` | Only after continuity PASS, and only into a **new** merged file |
| `nq_continuous_1m_lw_through_sep21.csv` | DATABENTO merge (new file) | Do not overwrite `phase58j/data/nq_continuous_1m_lw_extension.csv` |
| `nq_1m_ninjatrader_sep6_sep21.csv` | `NINJATRADER` / `CDX_ALIGNMENT_NINJATRADER` | **Never** |
| `rejected_not_used/` | TradingView NQ1! smoke | **Never** — incomplete and incompatible |

Every NinjaTrader row must carry `source=NINJATRADER`. Never relabel it DATABENTO.
