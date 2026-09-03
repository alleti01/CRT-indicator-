PHASE68 — DATA AVAILABILITY AUDIT
=================================

**Primary NQ 1M stack:** LEVEL 0 (OHLCV) — 3,136,946 bars
  Range: 2017-10-01 17:00:00-05:00 → 2026-08-28 15:59:00-05:00
  Fields: open, high, low, close, volume, contract, instrument_id, atr, rel_volume, vol_ma5

**Full-history microstructure:** LEVEL 0 — **DATA BLOCKED**
**Pilot microstructure (Phase27):** LEVEL 1 — 2024-01-01 23:00:00.055921057+00:00 → 2024-01-31 23:59:59.611470815+00:00

## Hard data gate

- Full-history Phase68: **STOP — DATA_BLOCKED_MICROSTRUCTURE**
- Pilot-only Phase68: **PROCEED (1 month trades)**

## Candidate datasets

### `phase27/data/raw/nq_trades_pilot_202401.csv`
- Size: 911.92 MB
- Level hint: 1
- Range: 2024-01-01 23:00:00.055921057+00:00 → 2024-01-31 23:59:59.611470815+00:00
- Trades: True | Aggressor: True | Quotes: False
- Columns: `ts_recv, timestamp, rtype, publisher_id, instrument_id, action, side, depth, price, size, flags, ts_in_delta...`

### `phase16/data/raw/nq_continuous_1m_20231201_20260626.csv`
- Size: 75.3 MB
- Level hint: 0
- Range: 2023-12-01 00:00:00+00:00 → 2026-06-26 20:59:00+00:00
- Trades: False | Aggressor: False | Quotes: False
- Columns: `timestamp, rtype, publisher_id, instrument_id, open, high, low, close, volume, symbol`

### `phase18/data/raw/nq_continuous_1m_raw.csv`
- Size: 88.27 MB
- Level hint: 0
- Range: 2020-12-01 00:00:00+00:00 → 2023-12-29 21:59:00+00:00
- Trades: False | Aggressor: False | Quotes: False
- Columns: `timestamp, rtype, publisher_id, instrument_id, open, high, low, close, volume, symbol`

### `phase16/data/raw/nq_continuous_1m_oos_20171001_20201201.csv`
- Size: 86.16 MB
- Level hint: 0
- Range: 2017-10-01 22:00:00+00:00 → 2020-11-30 23:59:00+00:00
- Trades: False | Aggressor: False | Quotes: False
- Columns: `timestamp, rtype, publisher_id, instrument_id, open, high, low, close, volume, symbol`

### `phase49/data/forward/nq_continuous_1m_forward.csv`
- Size: 0.0 MB
- Level hint: 0
- Range: nan → nan
- Trades: False | Aggressor: False | Quotes: False
- Columns: `timestamp, open, high, low, close, volume`

### `phase58j/data/nq_continuous_1m_lw_extension.csv`
- Size: 5.24 MB
- Level hint: 0
- Range: 2026-06-28 22:00:00+00:00 → 2026-08-28 20:59:00+00:00
- Trades: False | Aggressor: False | Quotes: False
- Columns: `timestamp, rtype, publisher_id, instrument_id, open, high, low, close, volume, symbol`

## Required data to unblock full Phase68

Purchase Databento GLBX.MDP3 `trades` schema for full NQ history (~$10/mo per month) to run Phase68 on full sample. Optional `mbp-1` (~$18/mo) for Families D/E quote features.

| Schema | Est. cost | Enables |
|--------|-----------|---------|
| `trades` (GLBX.MDP3) | ~$10/mo | P1–P10, Families A/B/C/F/G/H |
| `mbp-1` | ~$18/mo | Q1–Q8, Families D/E |
| `mbp-10` / `mbo` | higher | D1–D5 depth features |
