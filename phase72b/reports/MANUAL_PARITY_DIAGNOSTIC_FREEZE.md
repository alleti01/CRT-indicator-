# Phase72B-M — Manual Parity Diagnostic Freeze

Frozen: **2026-09-02**

## Pine hashes

| Stage | SHA256 (16) | Notes |
|-------|-------------|-------|
| **Before manual parity** | `ed1ab8e4fd020036` | After Phase72B CSV export layer only |
| **After manual parity** | `7c38c6dbcc811683` | Phase72B-M on-chart diagnostics added |

## Trading logic unchanged — confirmation

Layer A (`if barstate.isconfirmed and not TZ_WARN and bar_index >= WARMUP`, lines ~986–1271) was **not modified** in Phase72B-M.

All Phase72B-M code is appended **after** Layer A and existing Layer B blocks. It:

- Reads existing `var` state (`p58State`, `posState`, `lastAction`, feature cache series)
- Uses **new diagnostic-only** `var` names prefixed `p72b` (`p72bPrevSt`, `p72bPrevLastAction`)
- Does not assign to any trading `var` used by Layer A

Pure helper functions added (`f_p72bStateLbl`, `f_p72bArmTotal`) are read-only computations on existing series.

## Diagnostic additions (exact)

### Input group: `Phase72B Manual Parity`

| Input | Default |
|-------|---------|
| `manualParityMode` | false |
| `showParityTable` | true |
| `showEventLabels` | true |
| `showStateLabels` | false |
| `showForensicLabels` | false |
| `forensicStartMs` | 2026-08-26 13:00 Chicago |
| `forensicEndMs` | 2026-08-26 14:00 Chicago |
| `inspectTimestamp` | 2026-08-26 13:40 Chicago |
| `enableInspectBar` | false |

When `manualParityMode == false`, no table/labels/forensic output is created.

### On-chart parity table (top-left)

Fields: sym/tf, bar_index, unix_ms, UTC, Chicago, New York, O/H/L/C, ATR, STATE, ST before→after, inTrade/dir, cooldown, SIG/RAW/TAKE/ENT L/S, entry/ATR, stop/target, mins in trade, EXIT s/t/time, ctx, loc L/S, react L/S, ev L/S, decision, D/P4/H1, band/dom, GATES, lastAction.

### Event labels (`showEventLabels`)

Prefix **`AUTO `** (teal) — distinct from:
- Autonomous green/red `SIGNAL_*` / `ENTER_*` (existing Display group)
- Python ghosts (`PY SIG` fuchsia / `PY ENTRY` yellow)

### Forensic labels (`showForensicLabels`)

One compact label per bar inside `forensicStartMs`..`forensicEndMs`.

### Single-bar inspect (`enableInspectBar` + `inspectTimestamp`)

Detailed orange label on matching bar.

## Parity modes (tooling)

| Mode | CSV required? |
|------|----------------|
| `MANUAL_CHART_PARITY` | **No** |
| `CSV_PARITY` | Yes (optional if available) |

## Python tools added/updated

- `phase72b/tools/trace_timestamp.py` — T±N forensic trace
- `phase72b/diagnostics/manual_tv_observations.csv` — template (TV_MANUAL_REFERENCE only)
- `phase72b/reports/MANUAL_DIVERGENCE_LEDGER.csv` — divergence ledger template

## Verdict for this step

**MANUAL_PARITY_INFRASTRUCTURE_READY**
