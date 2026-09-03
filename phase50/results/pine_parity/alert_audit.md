# Phase 50 — Alert Audit

## Alert conditions

| Alert | Fires when | Once per event? |
|-------|------------|-----------------|
| LONG CONFIRMED | `p50LongConfirmed` pulse | Yes — reset each bar |
| SHORT CONFIRMED | `p50ShortConfirmed` pulse | Yes |
| LONG EXIT | `p50LongExit` pulse | Yes |
| SHORT EXIT | `p50ShortExit` pulse | Yes |
| PHASE44 LONG SETUP ACTIVE | New 15M accepted long setup | Yes (same bar) |
| PHASE44 SHORT SETUP ACTIVE | New 15M accepted short setup | Yes |
| B1 WINDOW EXPIRED | Window end without B1 | Yes |

## Verification

| Check | Result |
|-------|--------|
| Not every bar | Pulses cleared at bar open — **PASS** |
| Not before confirmation | B1 requires close break — **PASS** |
| Not retrospective | No `bar_index[n]` future refs for signals — **PASS** |
| Confirmed bar only | `barstate.isconfirmed` on 1M execution — **PASS** |

## Message format

Deterministic pipe-separated keys: `MODEL=PHASE50|SIDE=LONG|B1=CONFIRMED`

Extend via TradingView alert dialog with plot values when needed.
