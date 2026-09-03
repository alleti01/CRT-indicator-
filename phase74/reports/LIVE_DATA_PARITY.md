# Phase74 — Live vs Replay Data Parity

**Verdict:** `LIVE_REPLAY_DATA_PARITY_PASS`

---

## Objective

Prove that `StreamLiveDataProvider` (simulated live stream) produces identical closed `Bar` objects and derived values as `ReplayDataProvider` for the same recorded sequence.

---

## Method

Function: `compare_replay_live_parity()` in `phase74/market_data/live_provider.py`

1. Load synthetic NQ 1m dataframe via `phase73.replay.runner._synthetic_bars`
2. Initialize `ReplayDataProvider(df)` — ingests bar 0 on construction
3. Initialize `StreamLiveDataProvider(df)` — bootstraps bar 0 on `connect()` (matches replay warm-start)
4. For each subsequent bar: `replay.advance()` + `live.advance()`
5. Compare per bar: `open`, `high`, `low`, `close`, `volume`, `timestamp`
6. After bar 14: compare `atr()` (14-period)

---

## Bar Finalization Semantics

A 1-minute bar is **CLOSED** only when:

- `ingest_tick(bar, finalized=True)` is called, or
- `_finalize_row()` runs at simulated bar-end time (`bar_open + 1 minute`)

Incomplete bars are held in `_pending_bar` and **never** appended to `BarCache`.

Logged via `BarLifecycle`:

- `bar_start`, `bar_end`, `bar_received_at`, `bar_finalized_at`, `data_latency_ms`

Trader decisions requiring closed bars consume `BarCache.latest()` only.

---

## Connection States Detected

| State | Trigger |
|-------|---------|
| `DATA_CONNECTED` | `connect()` with data available |
| `DATA_DISCONNECTED` | `disconnect()` |
| `DATA_RECONNECTED` | `connect()` after prior disconnect |
| `DATA_STALE` | latency > staleness limit (default 90s) |
| `DATA_GAP` | missing minute in sequence |
| `DATA_DUPLICATE` | duplicate timestamp |
| `DATA_OUT_OF_ORDER` | timestamp regression |

Health enum maps to Phase73 `DataHealth` for engine compatibility.

---

## Results

```
python3 phase74/run_live.py --mode parity-check
→ LIVE_REPLAY_DATA_PARITY_PASS
```

Integration test `P74-01` passes on 80-bar comparison including ATR alignment.

---

## Production Live Path

`DatabentoLiveProvider` extends `StreamLiveDataProvider` and requires `DATABENTO_API_KEY`. Streaming ingestion must call `ingest_tick(..., finalized=True)` only at minute boundaries — same cache path as simulated stream.

Exchange/session metadata: `exchange="GLBX"`, timestamps internal UTC per Phase73 `Bar` contract.
