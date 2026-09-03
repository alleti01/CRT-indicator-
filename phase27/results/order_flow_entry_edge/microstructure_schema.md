# Phase 27 — Microstructure Schema Selection

## Selected schema: `trades` (Databento GLBX.MDP3)

### Rationale

Among schemas evaluated, **`trades`** is the minimum-cost source that enables causal **aggressor-side order flow** features. It is preferred over:

| Schema | Cost (1 mo) | Why not primary |
|---|---:|---|
| `ohlcv-1m` | lower | Already local; no aggressor side — Phase 26 failed |
| `trades` | **$10.43** | **Selected** — aggressor volume/delta/intensity |
| `mbp-1` | $17.69 | Book imbalance only; no aggressor classification |
| `tbbo` | ~similar to mbp | Combined but 2× cost vs trades-only pilot |
| `mbo` | much higher | Overkill for entry trigger discovery |

---

## Contract handling

| Item | Method |
|---|---|
| Symbol | `NQ.v.0` continuous (volume roll) |
| `stype_in` | `continuous` |
| Roll | Databento continuous symbology; use `symbol` / `instrument_id` columns |
| Timestamps | Exchange `ts_event` → UTC → `America/Chicago` for 5m boundaries |
| 5m aggregation | Floor `ts_event` to 5-minute bar end in Chicago time |
| Causality | Features at bar *t* use trades with `ts_event <= bar_close` |

---

## Aggressor side

Databento CME `trades` records include a **`side`** field:

- `A` = ask/seller aggressor (sell-initiated)
- `B` = bid/buyer aggressor (buy-initiated)
- `N` = no side / unknown

Features use exchange-provided side where available; `N` trades contribute to total volume/intensity but not directional delta.

---

## Feature families implemented (pilot)

### A. Aggressor flow
`buy_vol`, `sell_vol`, `delta`, `delta_norm`, `cum_delta_5m`, `delta_accel`

### B. Trade intensity
`trade_count`, `trades_per_sec`, `vol_per_sec`, `avg_trade_size`, `large_trade_pct`

### E. Price response
`price_change_atr`, `delta_price_response`, `flow_divergence`

### F. Short-term dynamics
Rolling over 30s / 1m / 2m / 5m / 10m causal windows ending at bar close

### OHLCV control (Model A)
Compact Phase-26-style features from existing NQ 5m bars (no microstructure).

---

## Not implemented (schema limitation)

- Spread, microprice, book imbalance (requires `mbp-1`)
- Multi-level depth (requires `mbp-10` / `mbo`)

---

## Alignment with NQ 5m decision grid

Primary decision timestamps = existing validated NQ 5-minute bar closes (Chicago).  
Microstructure features aggregated to the same bar index.  
Forward path labels computed from NQ 5m OHLCV (frozen ATR at decision bar).
