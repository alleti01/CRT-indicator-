# Phase51 Live Forward Paper Validation Report

## Status

| Item | Status |
|------|--------|
| Phase51 deployment package | **READY** |
| Frozen model manifest | **GENERATED** |
| Forward log templates | **READY** |
| Phase49 Python parity | **NOT READY** (no overlapping forward fills yet) |
| Auto trading | **OFF** |
| Paper trading | **READY** |

## Frozen model

- **Model hash:** `f29e61a82ef19fe21e13aa040035ca7bcabf7504f0477ebc4643253f7fd6f1f0`
- **Forward start CT:** `2026-08-26 11:30:00` (must match Pine input exactly)
- **B1 window:** 10 minutes
- **Symbol / timeframe:** NQ1! / 1-minute chart
- **Timezone:** America/Chicago

Verify before each evaluation run:

```bash
PYTHONPATH="/Users/anishalleti/CRT indicator" \
  python3 phase51/tools/generate_manifest.py --forward-start-ct "2026-08-26 11:30:00"
```

If hash changes without a new research phase → **MODEL DRIFT = FAIL**

## Architecture

```
CLOSED 15M CANDLE → Phase44 → WAIT B1 (10 min) → CLOSED 1M B1 → M0 → EXIT
```

Historical and realtime bars use the **same** `barstate.isconfirmed` code path. No `barstate.isrealtime` strategy branches.

## Canonical entry event

`p51LongEntryEvent` / `p51ShortEntryEvent` drive:

- Triangle markers
- Forward counters
- `alertcondition()` entries
- Dynamic `alert()` payload

## Historical functional test (Phase50 baseline — must remain)

On accessible TradingView history (Debug mode):

| Counter | Expected |
|---------|----------|
| P44 LONG | 4 |
| P44 SHORT | 1 |
| B1 WINDOWS | 5 |
| B1 LONG | 2 |
| B1 SHORT | 0 |
| LONG ENTRIES | 2 |
| SHORT ENTRIES | 0 |
| EXPIRED | 3 |

Re-verify after deploying Phase51 with **Forward start** set to a timestamp **after** loaded history (or enable Debug mode to compare cumulative counters).

## Forward-only log

Append-only CSVs (do not mix pre-deploy historical trades):

| File | Purpose |
|------|---------|
| `phase51/forward/phase44_signals.csv` | Phase44 setups after forward start |
| `phase51/forward/b1_events.csv` | B1 confirmations / expirations |
| `phase51/forward/trades.csv` | Closed trades with realized R |

Populate manually from alert payloads, or export Pine data-window plots (`P51_*` series).

## Benchmarks (Phase45 B1 — not optimization targets)

| Metric | Benchmark |
|--------|-----------|
| N | 1135 |
| AvgR | 1.648 |
| PF | 17.78 |
| MaxDD | 8.39 |
| Fill rate | 64.5% |
| Median B1 delay | 1.0 min |

## Checkpoints

Reports generated at 25 / 50 / 100 / 200 closed trades:

```bash
PYTHONPATH="/Users/anishalleti/CRT indicator" \
  phase16/.venv/bin/python phase51/tools/forward_metrics.py
```

## Phase49 parity (when overlapping data exists)

```bash
PYTHONPATH="/Users/anishalleti/CRT indicator" \
  phase16/.venv/bin/python phase51/tools/compare_python_pine.py
```

Output: `phase51/results/python_pine_forward_parity.csv`

## First live trade audit checklist

- [ ] SIGNAL ID recorded (e.g. `P51-00001`)
- [ ] Phase44 time CT, direction, class, setup
- [ ] B1 window start/end, confirmation time, delay
- [ ] Entry / stop / target match label and lines
- [ ] Exit time, price, type (SL / TP / TIME)
- [ ] Realized R computed from frozen levels
- [ ] Signal persists after chart reload
- [ ] Alert fired once (no duplicate on next bar)
- [ ] Logged to `phase51/forward/trades.csv` even if manually skipped (`user_taken=false`)

## Non-repaint reload test

After first live signal:

1. Record exact entry bar timestamp CT
2. Wait several bars
3. Refresh TradingView / remove & re-add indicator
4. Confirm marker still on same bar

If marker disappears → **NON-REPAINT TEST = FAIL**

## Phase50 preservation

Phase50 Pine at `phase50/pine/phase50_nq_indicator.pine` is **unchanged**. Phase51 is a separate live-forward layer.
