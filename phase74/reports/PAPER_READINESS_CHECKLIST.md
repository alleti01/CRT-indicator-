# Phase74 — Paper Readiness Checklist

**Current status:** Shadow-ready (`PHASE74_SHADOW_READY`)  
**External paper broker:** Not connected

---

## Pre-Flight Checklist

### Freezes
- [x] Pine SHA256 verified: `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f`
- [x] Phase73 engine freeze hashes match (`PHASE73_ENGINE_FREEZE.json`)
- [x] No Pine Layer A modifications in Phase74

### Data
- [x] `StreamLiveDataProvider` — closed 1m NQ bars, UTC
- [x] Bar finalization at minute boundary
- [x] Live/replay parity pass
- [ ] Databento live stream exercised in production (hook ready; key required)

### Webhook
- [x] Bearer token auth (`PHASE74_WEBHOOK_SECRET`)
- [x] Schema + Pine hash validation
- [x] Signal deduplication
- [x] Staleness + symbol + timeframe validation
- [x] Rate limiting
- [ ] HTTPS termination (reverse proxy / TLS cert — deploy-time)

### Execution
- [x] `PaperBrokerAdapter` (LOCAL_SIM)
- [x] `paper_mode` enforcement
- [x] Contract mapping explicit
- [x] Order idempotency
- [x] Fill-based entry management
- [x] CLIENT_SIDE_PROTECTION documented
- [ ] External paper broker (Tradovate/Rithmic) — **blocked on credentials**

### Safety
- [x] Position reconciliation
- [x] Daily loss limit
- [x] Kill switch
- [x] Emergency flatten
- [x] Restart recovery
- [x] Disconnect handling

### Observability
- [x] Live status JSON (`build_status`)
- [x] Latency tracker (pine→webhook→decision→order→fill)
- [x] Paper trade journal schema
- [x] Decision + event logging

### Testing
- [x] P74-01 through P74-26 integration tests pass
- [x] Phase73 T01–T24 regression pass

### Shadow Gate
- [x] Shadow mode operational
- [x] No broker orders in shadow
- [ ] 24h+ live shadow run with real TV alerts (operational, not CI)

---

## Commands

```bash
# Verify freezes + parity
python3 phase74/run_live.py --mode parity-check

# Shadow dress rehearsal
python3 phase74/run_live.py --mode shadow --bars 120

# Shadow + webhook listener
export PHASE74_WEBHOOK_SECRET="your-secret"
python3 phase74/run_live.py --mode shadow --webhook

# Paper (LOCAL_SIM) after shadow gate
python3 phase74/run_live.py --mode paper --bars 120

# Full test suite
python3 -m unittest phase74.tests.test_phase74_integration phase73.tests.test_phase73_scenarios -v
```

---

## Blockers to Full Paper PASS

| Blocker | Resolution |
|---------|------------|
| No Tradovate/Rithmic/NinjaTrader credentials | Provision paper account; implement venue adapter behind `PaperBrokerAdapter` interface |
| Databento live not exercised | Set `DATABENTO_API_KEY`; wire stream to `ingest_tick(finalized=True)` |
| HTTPS webhook in production | Deploy behind nginx/Caddy with TLS + secret rotation |

---

## Verdict Matrix

| Condition | Verdict |
|-----------|---------|
| All gates + external paper broker | `PHASE74_LIVE_PAPER_PASS` |
| All gates except external broker (current) | `PHASE74_SHADOW_READY` |
| Missing data/webhook/engine | `PHASE74_PARTIAL` or `PHASE74_FAIL` |

**Current verdict:** `PHASE74_SHADOW_READY`

---

## STOP Condition

Phase74 complete. Do **not** proceed to prop-firm or real-money deployment automatically.

Next: controlled forward paper dress rehearsal using this exact stack.
