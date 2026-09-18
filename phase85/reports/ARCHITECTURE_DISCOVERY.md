# Phase85 Architecture Discovery

Recorded before implementation. Inspected repository on 2026-09-18.

## Existing production flow

```
TradingView Phase72A  (TV_REVIEW/phase72a_autonomous_trader.pine)
        │ HTTPS webhook
        ▼
phase73 webhook receiver / validator / schemas
        │
        ▼
phase74 LiveStack  (wraps frozen Phase73 TraderEngine)
        │  live bars: StreamLiveDataProvider
        │  NT feed: CRTBarBridge.cs → NinjaTraderBridgeServer :8765
        │
        ├── Phase73 TAKE / PASS (engine + entry_quality)
        ├── Phase74 quality gates / day halt / trail overlay (paper/shadow)
        └── PaperBrokerAdapter → SlippageSimRouter → SimOrderRouter
                    │
                    ▼
              LOCAL_SIM fills only
              (run_live.py forces external_order_routing = false)
```

There is **no** NinjaTrader order path today. NT is market-data only.

## Existing abstractions (reuse, do not duplicate)

| Concern | Module | Role |
|---|---|---|
| Signal authority | `TV_REVIEW/phase72a_autonomous_trader.pine` | Frozen SHA256 `d75ff747…e32cc1f` |
| Pine freeze metadata | `phase73/config/PINE_SIGNAL_FREEZE.json` | Same hash; M0 1.0R / 2.5R / 60m / STOP_FIRST |
| Phase73 freeze | `phase74/config/PHASE73_ENGINE_FREEZE.json` + `verify_phase73_freeze()` | Hash-locks engine, webhook, M0, sim router, safety |
| TraderEngine | `phase73/trader/engine.py` | Frozen decision/management host |
| M0 | `phase73/trader/management.py` `build_management` / `evaluate_exit` | Canonical stop/target |
| Order router ABC | `phase73/execution/base.py` `OrderRouter` | `submit` / `flatten` |
| Sim fills | `phase73/execution/sim_router.py` | Immediate fill; not NT |
| Paper adapter | `phase74/execution/paper_broker.py` | LOCAL_SIM wrap of SimOrderRouter |
| Webhook idempotency | `phase74/execution/idempotency.py` | signal_id + action keys |
| NT bar protocol | `phase74/market_data/ninjatrader/protocol.py` | JSON-lines hello/bar/ack |
| NT bar server | `phase74/market_data/ninjatrader/bridge_server.py` | Python listens `127.0.0.1:8765`; NT connects |
| NT bar indicator | `phase74/market_data/ninjatrader/CRTBarBridge.cs` | Read-only; **no order APIs** |
| Contract mapping | `phase74/contracts/mapping.py` | Explicit; no silent NQ→MNQ |
| Phase73 safety | `phase73/risk/safety.py` | Kill / trading_enabled / paper_mode |
| Phase73 reconcile | `phase73/risk/reconciliation.py` | Engine vs broker snapshot |
| Phase74 config | `phase74/config/loader.py` | `shadow_mode`, `trading_enabled`, `external_order_routing` |
| Live stack | `phase74/runtime/live_stack.py` | Adapters around frozen engine; paper broker |

Transport convention: **JSON-lines over localhost TCP**. NinjaTrader is the TCP client; Python binds `127.0.0.1`. Phase85 keeps that polarity on a **separate port**.

## Integration points (adapter only)

Phase85 does **not** rewrite `TraderEngine`. Desired call shape:

```
LiveStack / rehearsal runner
    → Phase73 decision TAKE
    → ExecutionIntent
    → Phase85 safety gates
    → NinjaTraderExecutionAdapter
    → JSON-lines protocol
    → CRTExecutionBridge.cs
    → NinjaTrader Account.Submit
```

`OrderRouter.submit(order, market_price)` is a **synchronous paper-fill** contract. NT fills are asynchronous events. Phase85 therefore uses an **event-driven adapter**, not a drop-in replacement of `SimOrderRouter` inside `TraderEngine`.

## Frozen / must remain untouched

- `TV_REVIEW/phase72a_autonomous_trader.pine`
- Phase72A signal + ledger logic
- Phase73 entry / management / reversal (`phase73/trader/*` freeze set)
- Phase74 market-data decision behavior (`LiveStack` quality/trail/decision path)
- M0 (`build_management` / `evaluate_exit`)
- Phase83 / Phase84 research
- `CRTBarBridge.cs` market-data behavior and read-only guarantee

Pre-implementation checks (2026-09-18):

| Check | Result |
|---|---|
| Phase72A SHA256 | `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f` |
| `verify_phase73_freeze()` | PASS |
| CRTBarBridge SHA256 | `1a01a3f33c21cb3ac419e3ee7f3ab05448181b81a33bd5796f16ba2c6eeac880` |
| CRTBarBridge order APIs | none (`Submit` / `CreateOrder` / `EnterLong` / `Flatten` absent) |
| Frozen-file git dirty | none |

## New modules required

```
phase85/
  config.py + config/default.json
  protocol/          versioned JSON-lines commands + events
  execution/         intent, gates, state machine, adapter, M0 map, kill switch
  reconciliation/    position + order compare
  persistence/       command_id store, execution ledger, audit log
  ninjatrader/       CRTExecutionBridge.cs + Python server + fake harness
  diagnostics/       preflight + startup banners
  tests/
  reports/
```

## Modules that must remain untouched

All files listed in `PHASE73_ENGINE_FREEZE.json`, production Pine, `CRTBarBridge.cs`, Phase74 decision/runtime strategy behavior, Phase83/84.

## NinjaTrader 8 API notes (execution)

Inspected installed style from `CRTBarBridge.cs` (`NinjaTrader.Cbi`, `NinjaTrader.NinjaScript`). Public NT8 help-guide APIs used by `CRTExecutionBridge` (not invented wrappers):

- `Account.All`, `Account.Name`, `Account.Connection.Status`
- `Account.CreateOrder(...)`, `Account.Submit(Order[])`, `Account.Cancel(Order[])`, `Account.Flatten(Instrument[])`
- `Account.OrderUpdate`, `Account.ExecutionUpdate`, `Account.PositionUpdate`
- `Instrument.GetInstrument(string)`
- `OrderAction`, `OrderType`, `TimeInForce`, `OrderEntry`

If a compiled NT8 build rejects a signature, SIM checkout must stop with `PHASE85_NINJATRADER_API_BLOCKED` rather than inventing a second path.

## Default safety

Repository defaults remain fail-closed: `EXECUTION_MODE=SHADOW`, `SHADOW_MODE=true`, `TRADING_ENABLED=false`, `EXTERNAL_ORDER_ROUTING=false`, `NT_EXECUTION_BRIDGE_ENABLED=false`. No funded order is possible under defaults.
