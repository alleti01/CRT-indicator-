# Phase76 — Independent Causal Auction-Market Research

**Branch status:** Foundation complete — causality verified, discovery pipeline started.

## Quick start

```bash
# Checkpoint 00 — data audit
python3 phase76/diagnostics/run_data_audit.py

# Checkpoint 02 — prefix invariance (slow ~8–15 min on full history)
python3 phase76/diagnostics/run_causality_audit.py

# Checkpoints 01/03 + Family A/B path preview (slow ~10 min)
python3 phase76/diagnostics/run_discovery.py
```

## Rules

- Does **not** touch Phase72A, Phase73/74, or forward rehearsal
- Profile = **BAR_APPROX_PROFILE** (LEVEL 0 OHLCV only)
- No signal promotion until `CAUSALITY_PASS` + randomized controls + WF splits

## Reports

| Report | Purpose |
|--------|---------|
| `reports/PHASE76_DATA_AUDIT.md` | Data inventory |
| `reports/PHASE76_CAUSALITY_AUDIT.md` | Prefix invariance |
| `reports/PHASE76_DISCOVERY_PREVIEW.md` | Family A/B path preview (not final) |
| `reports/EXPERIMENT_LEDGER.csv` | Experiment log |
| `checkpoints/*.json` | Checkpoint PASS/FAIL |

## Module layout

```
phase76/python/
  config.py           — preregistered constants
  data_loader.py      — causal 1m stack
  sessions.py         — RTH session + overnight
  profile.py          — BAR_APPROX POC/VAH/VAL/HVN/LVN
  auction_engine.py   — incremental feature builder
  causality.py        — prefix audit
  market_states.py    — auction state machine
  signals.py          — families A–F
  path_audit.py       — MFE/MAE / first-passage
  entry.py            — T close → T+1 open entries
```

## Next steps (not yet run)

- Families C–F full evaluation
- S/R control experiment
- Matched + randomized controls
- Train / validation / exposed-historical-test splits
- Simple management grid
- Year/side stability
- Final verdict gates
