# Phase50 Accessible-History Validation Status

## Validation model

| Layer | Meaning | Current status |
|-------|---------|----------------|
| **Functional validation** | Pine pipeline fires on TV-loaded bars (counters + markers) | **PENDING** — user reads Debug dashboard on chart |
| **Exact historical parity** | Pine ↔ Python reference event match on same bars | **BLOCKED BY DATA ACCESS** |
| **Forward parity** | Pine ↔ Phase49 forward events after frozen start | **PENDING** — no overlapping forward fills yet |

## Data access constraint

- **Python reference ends:** `2026-06-25 14:31:00 America/Chicago`
- **TradingView accessible 1m history:** does not overlap reference period (plan limit)
- **Do not claim PASS or FAIL** on exact historical parity without overlapping bars

## Functional validation (TradingView)

On **NQ1! 1-minute**, enable **Debug mode** in indicator settings. Dashboard shows:

| Field | Meaning |
|-------|---------|
| FIRST BAR | Earliest loaded 1m bar timestamp |
| LAST BAR | Latest loaded 1m bar timestamp |
| P44 LONG / SHORT | Phase44 setup events (cumulative) |
| B1 WINDOWS | B1 wait windows started |
| B1 LONG / SHORT | B1 swing confirmations |
| LONG / SHORT ENTRIES | Entry markers emitted |
| EXPIRED | B1 windows expired without fill |

### Functional PASS criteria

- Substantial loaded history (not a handful of bars)
- At least one of: P44 events, B1 windows, B1 confirmations, or entries **> 0**
- LONG/SHORT **plotshape** markers visible on bars where entries > 0

### Functional FAIL criteria

- All counters remain **0** across substantial accessible history

Record your readings below after pasting latest Pine:

```
TRADINGVIEW ACCESSIBLE HISTORY:
FIRST BAR = [from dashboard]
LAST BAR = [from dashboard]

P44 LONG = 
P44 SHORT = 
B1 WINDOWS = 
B1 LONG = 
B1 SHORT = 
LONG ENTRIES = 
SHORT ENTRIES = 
EXPIRED = 

FUNCTIONAL HISTORICAL PIPELINE: PASS / FAIL
HISTORICAL MARKERS VISIBLE: YES / NO
```

## Exact parity

```
HISTORICAL EXACT PARITY: BLOCKED BY DATA ACCESS
```

## Forward parity (primary path)

Frozen forward start: `2026-06-29 00:00:00 America/Chicago` (Phase49)

When Phase49 `forward_signals.csv` contains filled B1 events **and** Pine export overlaps:

```bash
PYTHONPATH="/Users/anishalleti/CRT indicator" \
  phase16/.venv/bin/python phase50/tools/compare_forward_pine_python.py \
  --pine-export /path/to/tv_forward_export.csv
```

Output: `phase50/results/pine_parity/forward_pine_python_comparison.csv`

Forward parity requires per-event:
- direction exact match
- B1 timestamp exact (±1 minute documented)
- entry timestamp exact
- entry/stop/target within NQ tick tolerance (`0.25`)

**STRATEGY LOGIC CHANGED:** NO
