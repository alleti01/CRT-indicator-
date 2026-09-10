# Pine baseline — paper run started 2026-09-09

**Purpose:** Compare today's Pine vs updated Pine (2026-09-10+) on Friday.

| Field | Value |
|-------|--------|
| **pine_hash** | `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f` |
| **Script** | `TV_REVIEW/phase72a_latency_audit.pine` |
| **Bot mode** | `--mode paper` (LOCAL_SIM + slippage + pass-chase/late) |
| **Paper journal** | `phase74/logs/paper_trades.csv` |
| **Bar log** | `phase74/logs/bars.csv` |

## Before switching Pine tomorrow

1. Stop paper bot (Ctrl+C or kill python on 8765/8787)
2. Archive baseline logs:
   ```powershell
   Copy-Item phase74\logs\paper_trades.csv forward_rehearsal\reports\baseline_2026-09-09_paper_trades.csv
   Copy-Item phase74\logs\bars.csv forward_rehearsal\reports\baseline_2026-09-09_bars.csv -ErrorAction SilentlyContinue
   python scripts/validate_shadow_signals.py 2026-09-09 --sequential --pass-chase --pass-late
   ```
3. Update Pine in TV, note **new pine_hash**, update alerts
4. Restart paper: `.\scripts\start-ninjatrader-paper.ps1`

## Friday compare

```powershell
python scripts/compare_paper_replay.py 2026-09-09   # baseline day
python scripts/compare_paper_replay.py 2026-09-10   # new pine day(s)
```

Compare total gross R, win rate, and trade count from archived `paper_trades.csv` files.
