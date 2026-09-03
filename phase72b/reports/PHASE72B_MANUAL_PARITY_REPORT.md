# Phase72B Manual Parity Report

Status: **MANUAL_PARITY_INFRASTRUCTURE_READY** (no events inspected yet)

## Purpose

Manual on-chart Pine ↔ Python parity without TradingView CSV export.

Ground truth: **autonomous Pine** (`phase72a_autonomous_trader.pine`) via Manual Parity table and AUTO labels.  
NOT ground truth: Python review ghosts, frozen Phase59/60 stream.

## Parity mode

`MANUAL_CHART_PARITY` — default in `run_phase72b_parity.py`

## Inspection log

| # | Timestamp (CHI) | Pine event | Python event | OHLC | ATR | Features | State | Signal | Entry | Exit | First diff | Root cause | Fix | Rerun |
|---|-----------------|------------|--------------|------|-----|----------|-------|--------|-------|------|------------|------------|-----|-------|
| — | *(pending)* | | | | | | | | | | | | | |

Record TV readings in `phase72b/diagnostics/manual_tv_observations.csv` with `source=TV_MANUAL_REFERENCE`.

## Workflow

1. OHLC → ATR → FEATURES → STATE → SIGNAL → ENTRY → EXIT
2. FIRST DIVERGENCE → ROOT CAUSE → FIX → FULL RERUN
3. Never patch individual trades

## Python trace command

```bash
python3 phase72b/tools/trace_timestamp.py \
  --timestamp "2026-08-26 13:40:00" \
  --timezone America/Chicago \
  --before 10 \
  --after 10
```

## Distinction: manual vs full parity

| Level | Meaning |
|-------|---------|
| MANUAL_FORENSIC_PARITY | Bar-by-bar agreement in inspected windows |
| FULL_EVENT_STREAM_PARITY | All events over full overlap (requires scale validation later) |

Do not claim FULL_EVENT_STREAM_PARITY from screenshots alone.

## Checkpoints

See `phase72b/checkpoints/` — checkpoint 00 complete; 01–11 pending user observations.
