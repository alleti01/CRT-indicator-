# Forward Rehearsal — Operational Guide

**Status:** Infrastructure ready — awaiting real TradingView alerts + Databento live key for Stage A

---

## Freeze

Every session verifies `forward_rehearsal/FREEZE_MANIFEST.json`:

```bash
python3 forward_rehearsal/run_forward.py --verify-freeze
python3 forward_rehearsal/run_forward.py --write-freeze   # regenerate after intentional changes
```

Hashes cover:
- `TV_REVIEW/phase72a_autonomous_trader.pine`
- Phase73 TraderEngine modules
- Phase74 adapters
- Paper execution adapter
- Forward rehearsal runtime

**No silent code changes during an active session.**

---

## Stage A — Live Shadow (real TV + real data)

### Prerequisites

1. Copy `forward_rehearsal/.env.example` → `.env` (never commit)
2. Set `PHASE74_WEBHOOK_SECRET` — TradingView alert webhook Bearer token
3. Set `DATABENTO_API_KEY` — live NQ 1m feed
4. Configure TradingView Phase72A alert → HTTPS webhook (use reverse proxy for TLS in production)
5. Verify Pine hash matches manifest

### Run

```bash
export PHASE74_WEBHOOK_SECRET="your-secret"
export DATABENTO_API_KEY="your-key"
python3 forward_rehearsal/run_forward.py --stage shadow --use-databento
```

Optional resilience tests during shadow:

```bash
python3 forward_rehearsal/run_forward.py --stage shadow --use-databento --restart-test --disconnect-test
```

### Expected outputs

- `WOULD_ENTER_LONG` / `WOULD_ENTER_SHORT`
- `WOULD_HOLD_*` / `WOULD_EXIT_STOP` / `WOULD_EXIT_TARGET` / `WOULD_EXIT_TIME`
- `WOULD_PASS_*` for filtered signals
- **Zero broker orders** — position stays FLAT

### Gate: `FORWARD_SHADOW_PASS`

Written to `forward_rehearsal/gates/FORWARD_SHADOW_PASS` when:

- Real TV alerts received
- Live data healthy
- All signals reconciled (no duplicate execution)
- State machine stable
- No real orders sent

---

## Stage B — Local Paper (after shadow pass)

```bash
python3 forward_rehearsal/run_forward.py --stage local-paper --use-databento
```

Blocked until `forward_rehearsal/gates/FORWARD_SHADOW_PASS` exists.

Creates actual LOCAL_SIM positions with M0 management (1.0 ATR stop, 2.5R target, 60m max hold).

---

## Stage C — External Paper

**Do not start automatically.**

Inspect intended prop-firm platform (Tradovate / Rithmic / NinjaTrader) before building adapter.

Requires `EXECUTION_MODE_UNVERIFIED` block until paper account proven.

---

## Session Logs

Immutable logs per session:

```
forward_rehearsal/sessions/YYYY-MM-DD/<session_id>/
  signals.jsonl
  market_health.jsonl
  decisions.jsonl
  orders.jsonl
  fills.jsonl
  positions.jsonl
  errors.jsonl
  shadow_events.jsonl
  state_transitions.jsonl
  session_summary.json
  latency_audit.json
```

---

## Reports (auto-generated on finalize)

| Report | Path |
|--------|------|
| Signal reconciliation | `forward_rehearsal/reports/SHADOW_SIGNAL_RECONCILIATION.csv` |
| Entry price audit | `forward_rehearsal/reports/SHADOW_ENTRY_PRICE_AUDIT.csv` |

---

## Infrastructure tests (synthetic allowed)

```bash
python3 -m unittest forward_rehearsal.tests.test_forward_infrastructure -v
python3 forward_rehearsal/run_forward.py --stage infra-test --restart-test
```

Synthetic signals are **rejected** in shadow/local-paper stages unless context is infra-test.

---

## Bug classification (mandatory)

| Observation | Classification |
|-------------|----------------|
| Signal loses / stops out | `STRATEGY_BEHAVIOR` |
| Late-looking signal | `STRATEGY_BEHAVIOR` |
| Duplicate webhook order | `SYSTEM BUG` → fix only the bug |
| ATR wrong | `DATA_BUG` |
| Restart doubles position | `PERSISTENCE_BUG` |

**Do not optimize strategy from forward observations.**

---

## Current verdict

`INFRASTRUCTURE_READY` — run Stage A with real TV + Databento to achieve `FORWARD_SHADOW_PASS`.
