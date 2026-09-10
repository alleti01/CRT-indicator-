# Missed-Reversal / Signal Quality Ledger

Offline batch tool that labels bars with **Pine-native** Phase72A gate states, cost-adjusted hypothetical M0 outcomes, and a four-bucket classification.

**Trust status:** All ledger output is labeled `PENDING_REPLAY_CONFIRMATION` until manual TradingView bar-replay checklist is completed. Gate rankings are **not final**.

**Does not modify** frozen `TV_REVIEW/phase72a_autonomous_trader.pine`.

## Gate source (Fix 2)

Gate states come from **`TV_REVIEW/phase72a_signal_ledger.pine`** Layer D:

1. **All bars:** Export chart CSV with `GLD_*` data-window plots → parsed by `gate_export.py`
2. **Signal-fired bars:** Alert JSON (schema 1.2) embeds `gate_state` keyed to `event_id`

No Phase72B Python mirror is used.

All timestamps in alerts, exports, and ledger rows are **UTC only** (`GLD_bar_time_utc_ms` / `*_utc_ms` fields).

## What it does

| Column | Description |
|--------|-------------|
| `bar_time_utc` | UTC ISO timestamp |
| `signal_fired` | From signal log or `GLD_take_*` export |
| `direction_fired` | `long`, `short`, or null |
| `event_id` | Alert event id when available |
| `gate_state` | JSON dict of 14 TAKE-chain booleans (Pine-native) |
| `hyp_long_R` / `hyp_short_R` | Offline **net** M0 R (phase73 management + `NQ.cost_r`) |
| `classification` | `correct_take`, `false_positive`, `missed_reversal`, `correct_pass` |
| `trust_status` | Always `PENDING_REPLAY_CONFIRMATION` until replay checklist done |

### Entry / M0 convention

- Signal at bar **T** close → hypothetical fill at **T+1 open**
- M0: phase73 `build_management` + `evaluate_exit` (1.0R stop, 2.5R target, 60m hold, STOP_FIRST)
- Net R: gross R minus `NQ.cost_r` (same as phase69 `walk_trade`)

## Build the ledger

```bash
# 1. Load phase72a_signal_ledger.pine on NQ1! 1M, export chart CSV with GLD plots
python3 -m signal_ledger.ledger_builder \
  --start 2026-08-28 \
  --end 2026-08-28 \
  --gate-export path/to/tv_chart_export.csv \
  --output signal_ledger/output/ledger.parquet \
  --threshold-r 1.5 \
  --signals phase74/logs/signals.jsonl
```

## Recompute gate offsets (Part B)

```bash
python3 signal_ledger/tools/recompute_gate_offsets.py \
  --gate-export path/to/tv_chart_export.csv
```

## Aggregate gates

```bash
python3 -m signal_ledger.gate_aggregate \
  --ledger signal_ledger/output/ledger.parquet \
  --out-missed signal_ledger/output/gates_missed_reversal.csv \
  --out-fp signal_ledger/output/gates_false_positive.csv
```

Prints `NOT FINAL — pending TV bar-replay confirmation`.

## Tests

```bash
pytest signal_ledger/tests/ -q
```

## Out of scope

- Changing what Phase72A fires
- Live execution
- Presenting gate rankings as causal/final before replay confirmation
