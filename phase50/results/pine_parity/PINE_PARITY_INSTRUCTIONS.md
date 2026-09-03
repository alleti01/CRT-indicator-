# Phase 50 — Pine Parity Instructions

## Goal

Event-by-event parity between TradingView Pine and Python reference (`python_reference_signals.csv`).

## Setup

1. **Symbol:** `CME_MINI:NQ1!` (or continuous NQ matching CME ETH session)
2. **Chart timeframe:** **1 minute**
3. **Timezone:** America/Chicago (exchange)
4. **Indicator:** `phase50/pine/phase50_nq_indicator.pine`

## Export Pine events

TradingView does not export indicator state directly. Use **debug mode**:

1. Enable **Debug mode (parity export codes)** in indicator settings
2. Use **Chart → Export chart data** or **Strategy Tester** (if using validation strategy)
3. Export plots: `P50_EVENT_CODE` (+1 LONG, -1 SHORT), `P50_ENTRY`, `P50_STOP`, `P50_TARGET`
4. Convert export CSV to format:

```csv
signal_id,phase44_timestamp,direction,phase44_class,setup_type,b1_window,b1_timestamp,b1_delay,entry_timestamp,entry_price,stop,target,exit_timestamp,exit_price,exit_type
```

Alternatively use **alert log** for forward paper (Phase49) — not for full historical parity.

## Compare

```bash
phase16/.venv/bin/python phase50/tools/compare_pine_python.py \
  --python-ref phase50/results/pine_parity/python_reference_signals.csv \
  --pine-export /path/to/pine_export.csv \
  --output phase50/results/pine_parity/full_parity_results.csv
```

## Sample first

Use `sample_parity_reference.csv` (~40–80 events) before full history.

## Tolerances

| Field | Rule |
|-------|------|
| Timestamps | Exact 1M match preferred |
| Prices | ±0.25 pt (1 NQ tick) |
| Direction/class/setup | Exact |
| Exit type | Exact |

## Regenerate Python reference

```bash
phase16/.venv/bin/python -m phase50.run
```

## Regenerate Pine from Phase44 template

```bash
phase16/.venv/bin/python phase50/tools/generate_pine_indicator.py
```
