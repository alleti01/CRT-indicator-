# Phase73 — Production Trader Foundation

**Verdict:** `PHASE73_PRODUCTION_FOUNDATION_PASS`

**Date:** 2026-09-03

---

## Architecture

```
TRADINGVIEW/PINE SIGNAL (authoritative)
        ↓ webhook JSON
phase73/webhook/receiver.py
        ↓ validated PineSignal
phase73/trader/engine.py  (TraderEngine — single engine)
        ↕
phase73/market_data/provider.py  (ReplayDataProvider → future LiveDataProvider)
        ↓
phase73/trader/entry_quality.py
phase73/trader/management.py  (M0 benchmark)
        ↓
phase73/execution/sim_router.py
        ↓
phase73/logging/* + phase73/persistence/state.py
```

**Principle:** Pine finds the opportunity. Live/replay market data tells Python what the market is doing now. Python decides valid execution and manages the position. The broker (sim today) executes.

---

## Pine freeze

| Item | Value |
|------|-------|
| File | `TV_REVIEW/phase72a_autonomous_trader.pine` |
| SHA256 | `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f` |
| Config | `phase73/config/PINE_SIGNAL_FREEZE.json` |
| Authority doc | `phase73/reports/PINE_SIGNAL_AUTHORITY.md` |

Layer A is frozen. Hash mismatch → `SIGNAL_HASH_MISMATCH`.

---

## Signal contract

Schema version `1.0`. Required fields validated in `phase73/webhook/validator.py`.

Reason codes:

- `WEBHOOK_VALID`
- `WEBHOOK_INVALID`
- `SIGNAL_DUPLICATE`
- `SIGNAL_STALE`
- `SIGNAL_WRONG_SYMBOL`
- `SIGNAL_WRONG_TIMEFRAME`
- `SIGNAL_HASH_MISMATCH`

Test harness: `python3 phase73/webhook/test_harness.py`

---

## Market data contract

Provider interface: `phase73/market_data/base.py`

| Provider | Status |
|----------|--------|
| `REPLAY_DATA_PROVIDER` | Functional (local 1m / synthetic) |
| `LIVE_DATA_PROVIDER` | Stub — Phase74 |

Health states: `DATA_HEALTHY`, `DATA_STALE`, `DATA_MISSING`, `DATA_GAP`, `DATA_OUT_OF_ORDER`

No entry when unhealthy.

---

## Trader FSM

States and actions defined in `phase73/trader/fsm.py`.

Core flow:

1. `FLAT` → signal received → entry quality check
2. `TAKE_*` → sim order → `LONG_ACTIVE` / `SHORT_ACTIVE`
3. M0 management → exit → `FLAT`
4. Opposite signal → `REVERSAL_WATCH_*` (auto-reverse **disabled** by default)

---

## Execution model

- `SimOrderRouter` — immediate simulated fills, full order state machine preserved
- Order states: CREATED → SUBMITTED → ACKNOWLEDGED → FILLED (or REJECTED)
- No real-money connectivity

---

## Position reconciliation

`PositionBook`: desired / internal / broker

Mismatch → `POSITION_MISMATCH` → halt new entries (configurable)

---

## M0 management (frozen)

| Parameter | Value |
|-----------|-------|
| Stop | 1.0 ATR |
| Target | 2.5R |
| Max hold | 60 minutes |
| Same-bar collision | STOP_FIRST |

Time-progress exit (T5): **disabled** (`enable_time_progress_exit: false`)

---

## Safety model

Defaults (`phase73/config/default.json`):

- `trading_enabled: false`
- `paper_mode: true`
- `kill_switch: false`
- `max_positions: 1`
- `auto_reverse_enabled: false`

---

## Restart / recovery

`phase73/persistence/state.py` persists open position, stops, targets, MFE/MAE, bars in trade.

On startup `TraderEngine._restore()` reloads state — never assumes FLAT.

---

## Logging / event store

| File | Content |
|------|---------|
| `decisions.jsonl` / `decisions.csv` | Every bar/event decision |
| `signals.csv` | Webhook signals |
| `orders.csv` | Order lifecycle |
| `fills.csv` | Sim fills |
| `positions.csv` | Position snapshots |
| `errors.csv` | Validation/reconciliation errors |

---

## Replay engine

`phase73/replay/runner.py` — same `TraderEngine` as webhook mode.

```bash
python3 phase73/run_trader.py --mode replay --bars 120
python3 phase73/run_trader.py --mode local-webhook
```

---

## Automated tests

`phase73/tests/test_phase73_scenarios.py` — T01–T24 + hash mismatch + same-engine check.

```bash
python3 -m unittest phase73.tests.test_phase73_scenarios -v
```

---

## Hard pass gates

| Gate | Status |
|------|--------|
| Pine signal authority frozen/hash recorded | PASS |
| Webhook schema deterministic | PASS |
| Duplicate signals cannot double-enter | PASS |
| Replay data feeds sequentially | PASS |
| Market-data health works | PASS |
| Trader FSM deterministic | PASS |
| M0 management works | PASS |
| STOP_FIRST works | PASS |
| Sim orders/fills work | PASS |
| Position reconciliation works | PASS |
| Restart recovery works | PASS |
| Safety invariants work | PASS |
| Decision logs reconstruct trades | PASS |
| Automated test suite passes | PASS |
| Replay and webhook use SAME TraderEngine | PASS |
| No real-money connectivity | PASS |

---

## Known limitations

1. **Live data / broker** — not connected (Phase74)
2. **PASS_LATE / PASS_CHASE** — architecture present, disabled (no invented thresholds)
3. **Auto-reverse** — disabled by default; opposite signals recorded only
4. **Trading disabled by default** — must set `trading_enabled: true` for replay/webhook execution
5. **Webhook** — localhost only (`127.0.0.1:8787`)

---

## Next steps (Phase74)

- `LIVE_DATA_PROVIDER` adapter
- Paper broker adapter (Tradovate/Rithmic/etc.)
- Same `TraderEngine` — no separate backtest implementation

---

## Directory structure

```
phase73/
  config/          PINE_SIGNAL_FREEZE.json, default.json, loader.py
  webhook/         receiver, validator, schemas, deduplicator, test_harness
  market_data/     bar, base, provider, cache, health
  trader/          fsm, engine, entry_quality, management
  execution/       sim_router, orders, positions, fills
  risk/            safety, reconciliation
  logging/         decision_logger, event_store
  persistence/     state.py
  replay/          runner.py
  tests/           test_phase73_scenarios.py
  reports/         this file + PINE_SIGNAL_AUTHORITY.md
  run_trader.py
```
