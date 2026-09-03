# Phase 27 — Data Cost Audit

**Date:** 2026-08-21  
**Status:** No local NQ microstructure data found. Download gated per Phase 27 spec.

---

## Local inventory (pre-download)

| Asset | Schema | Location | Usable for order flow? |
|---|---|---|---|
| NQ 5m OHLCV | aggregated bars | `phase16/data/processed/nq_5m*.csv` | **No** — Phase 26 exhausted |
| NQ 1m OHLCV | `ohlcv-1m` | `phase16/data/raw/nq_continuous_1m*.csv` | **No** — volume only |
| ES 1m OHLCV | `ohlcv-1m` | `phase24/data/raw/es_continuous_1m.csv.parts/` | **No** — wrong product |
| CRT `trades.csv` | backtest outputs | `phase16/results/**/trades.csv` | **No** — simulated trades |
| MBP/MBO/TBBO/trades ticks | — | **Not present** | — |
| `.dbn` / `.zst` / parquet ticks | — | **Not present** | — |

**Conclusion:** Order-flow research requires new Databento acquisition.

---

## Databento cost estimates (NQ.v.0, GLBX.MDP3, continuous)

| Schema | Range | Est. cost | vs $20 gate |
|---|---|---:|---|
| **trades** | 2024-01-01 → 2024-02-01 (1 mo) | **$10.43** | ✅ proceed |
| trades | 2024-01-01 → 2024-03-01 (2 mo) | $20.58 | ❌ approval |
| trades | 2024-01-01 → 2024-04-01 (3 mo) | $30.21 | ❌ approval |
| trades | 2024-01-01 → 2024-07-01 (6 mo) | $61.05 | ❌ approval |
| **mbp-1** | 2024-01-01 → 2024-02-01 (1 mo) | **$17.69** | ✅ proceed |
| mbp-1 | 2024-01-01 → 2024-07-01 (6 mo) | $102.64 | ❌ approval |
| tbbo | 2024-01-01 → 2024-07-01 (6 mo) | $101.75 | ❌ approval |

Downloader: `phase16/download_databento.py` (`--estimate-only`, `--max-cost-usd`).

---

## Recommended pilot (in-budget)

| Field | Value |
|---|---|
| **DATASET** | GLBX.MDP3 |
| **SCHEMA** | **trades** |
| **SYMBOL** | NQ.v.0 (continuous) |
| **PROPOSED RANGE** | 2024-01-01 → 2024-02-01 |
| **ESTIMATED COST** | **$10.43** |
| **ESTIMATED SIZE** | ~millions of trade rows (tick-level) |

### Features possible with `trades`

- Buy/sell-initiated volume (Databento `side` field when present)
- Volume delta, normalized delta, cumulative delta
- Trade intensity (trades/sec, vol/sec)
- Average trade size, large-trade counts
- Delta acceleration / persistence (causal windows)
- Price response to flow (Δprice per delta unit)
- Flow-price divergence diagnostics

### Features NOT possible with `trades` alone

- Bid/ask spread, top-of-book sizes
- Level-1 / multi-level book imbalance
- Depth replenishment / pulling
- Microprice from BBO

### Why `trades` is sufficient for Phase 27 hypothesis

The core question is whether **aggressor order flow** adds incremental predictive power over OHLCV. The `trades` schema is the **lowest-cost** schema that provides exchange-reported aggressor side and tick-level intensity — the primary order-flow information class. Book state (`mbp-1`) is a secondary upgrade ($17.69/month) testable only after trades pilot succeeds.

---

## Pilot limitations

- ~**22 RTH sessions** in 1 calendar month — below the 100-day preference.
- Walk-forward within January only (train first half → validate second half).
- If pilot fails early-stop criteria, **do not** expand to 2–6 month data without approval.

---

## Expansion estimates (if pilot passes)

| Range | trades cost |
|---|---:|
| 6 months (2024-H1) | $61.05 |
| 12 months | ~$120+ (extrapolated) |

All expansion **> $20** → requires explicit approval before download.
