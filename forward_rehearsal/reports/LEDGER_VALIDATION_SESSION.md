# Ledger validation session — started 2026-09-10

**Status:** IN PROGRESS (TV steps require you)

## Pre-checks (automated — DONE)

| Check | Result |
|-------|--------|
| Production Pine hash | `d75ff747…` ✓ MATCH |
| `phase72a_signal_ledger.pine` exists | ✓ |
| `signal_ledger/tests/` | 31 passed |
| Paper bot (8765/8787) | running |
| ngrok | `https://finale-streak-bucket.ngrok-free.dev` |

## Webhook URLs

**Chart A — production trading:**
```
https://finale-streak-bucket.ngrok-free.dev/webhook?token=471ab31a4b0724cef0a3e66b05bdf577cc32a58ae52acaa4f05f353ddd6d93c5
```

**Chart B — ledger gate JSON (diagnostic only, no trades):**
```
https://finale-streak-bucket.ngrok-free.dev/webhook/ledger?token=471ab31a4b0724cef0a3e66b05bdf577cc32a58ae52acaa4f05f353ddd6d93c5
```

Logs to: `phase74/logs/ledger_alerts.jsonl` + `ledger_alerts.csv`

### Chart B alert setup (no TV CSV export needed)
1. Indicator settings → turn **ON** `Fire SIGNAL alerts with gate_state JSON`
2. Create alert → **Any alert() function call** on ledger indicator
3. Webhook URL = **ledger URL above** (not production URL)
4. Message = `{{strategy.order.alert_message}}` or leave default if TV sends alert body

---

## Your TV setup checklist

- [ ] Chart A: `phase72a_autonomous_trader.pine` on NQ1! 1m
- [ ] Chart B: `phase72a_signal_ledger.pine` on same NQ1! 1m
- [ ] Chart B: `Export gate booleans to Data Window (GLD_*)` = ON
- [ ] Chart B: `Fire SIGNAL alerts with gate_state JSON` = OFF
- [ ] Data Window shows `GLD_take_long`, `GLD_take_short`, etc.

---

## Signal parity log

Fill `LEDGER_SIGNAL_PARITY_LOG.csv` as signals fire (or paste rows below).

| # | Time ET | Prod dir | Ledger dir | Match? | Notes |
|---|---------|----------|------------|--------|-------|
| | | | | | |

Target: ≥20 events (5+ LONG, 5+ SHORT minimum).

---

## Bar Replay (Chart B)

- [ ] Region 1: LONG TAKE — no gate backdating
- [ ] Region 2: SHORT TAKE
- [ ] Region 3: reversal/chop
- [ ] Region 4: pivot/swing
- [ ] Region 5: quiet

---

## Export + Python

When ready, export Chart B CSV to:

`forward_rehearsal/reports/phase72a_ledger_tv_export_2026-09-10.csv`

Then run:

```powershell
.\scripts\run-ledger-export-checks.ps1 -CsvPath "forward_rehearsal\reports\phase72a_ledger_tv_export_2026-09-10.csv"
```

---

## Final verdict

- [ ] PASS — document date + sign-off
- [ ] FAIL — record in Section 19 format (docs/WINDOWS_PHASE72A_LEDGER_VALIDATION.md)

---

## Paper baseline (parallel track)

| File | Purpose |
|------|---------|
| `baseline_2026-09-09_paper_trades.csv` | Sep 9 baseline (+4.50R archived) |
| `2026-09-09_TRADE_LOG.md` | Loss analysis |
| `PINE_BASELINE_2026-09-09.md` | Swap checklist for new Pine |
