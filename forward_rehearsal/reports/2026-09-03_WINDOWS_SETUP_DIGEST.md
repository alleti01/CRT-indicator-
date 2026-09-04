# Windows Forward Rehearsal — Session Digest (2026-09-03)

Compiled from bot logs, ngrok traffic, forward-rehearsal session summaries, and setup notes from today's Windows migration session.

**Bottom line:** Infrastructure is working (bot, ngrok, TradingView delivery path). **Zero TradingView alerts were accepted.** All 30 live webhook attempts returned **409 Conflict** due to alert JSON timestamp/placeholder issues — not connectivity.

---

## Executive summary

| Area | Result |
|------|--------|
| Repo cloned on Windows | OK |
| Python 3.12 + deps | OK |
| CRLF → LF freeze fix (~3087 files) | OK |
| Bot starts shadow mode + Databento | OK |
| Webhook listening `127.0.0.1:8787/webhook` | OK |
| ngrok tunnel (v3.39.9) | OK |
| TradingView → ngrok → bot path | OK (30 POSTs received) |
| Valid TradingView signal accepted | **0** |
| `FORWARD_SHADOW_PASS` gate | **Not reached** |

---

## What went right

### 1. Environment & freeze

- Project cloned to `C:\Users\allet\Trading Bot`
- Python 3.12 installed; bot runs via full path when `python` not on PATH
- **FREEZE_MANIFEST_MISMATCH** fixed by converting Windows CRLF line endings to LF across frozen files
- `PHASE73_ENGINE_FREEZE` passes after bulk LF conversion
- Env vars set in PowerShell (not bash `export`):
  - `DATABENTO_API_KEY` — live feed key configured
  - `PHASE74_WEBHOOK_SECRET` — webhook auth secret configured (ends in `…d93c5`)

### 2. Bot runtime

Long-running shadow session started **2026-09-03 01:34 ET** (background process):

```
secure webhook listening 127.0.0.1:8787/webhook
forward webhook listening
FORWARD REHEARSAL stage=shadow session=20260903T045154Z-8809df5c
  data=Databento live
  synthetic_allowed=False
```

Terminal 1 also shows later restarts at 00:59 ET and 01:58 ET.

### 3. ngrok

- Initial ngrok v3.3.1 failed (account requires ≥3.20.0)
- Microsoft Store ngrok **v3.39.9** works
- Tunnel online: `https://finale-streak-bucket.ngrok-free.dev` → `http://localhost:8787`
- TradingView webhook URL pattern:
  `https://finale-streak-bucket.ngrok-free.dev/webhook?token=<PHASE74_WEBHOOK_SECRET>`

### 4. Internal / synthetic tests (early UTC morning)

These prove the **engine** works when payloads are valid:

| Session ID | Stage | Result |
|------------|-------|--------|
| `20260903T034825Z-98869d1a` | infra-test | 1 synthetic signal → `WOULD_ENTER`, MATCH |
| `20260903T034844Z-4526c1df` | infra-test | Restart + disconnect tests → `INFRA_TEST_COMPLETE` |
| `20260903T034825Z-efcc6f07` | local-paper | 1 synthetic signal processed (blocked gate path) |

Synthetic signal in logs (`phase74/logs/signals.jsonl`): `WOULD_ENTER` shadow event recorded — engine path OK.

### 5. TradingView connectivity (the important part)

TradingView **did reach the bot** — 30 POST requests logged by ngrok, all with:

- `User-Agent: TradingView Webhook`
- Correct webhook path + `?token=` auth
- JSON content-type

So the Mac→Windows migration networking stack is **not** the blocker.

---

## What went wrong

### Root cause chain

All live TradingView failures are **alert message content**, not bot bugs:

```
Phase 1 (most of day)  → static timestamps "2026-01-01T00:00:00Z"
                         → bot rejects: SIGNAL_STALE (age ~245 days, limit 120s)
                         → TradingView shows: 409 Conflict

Phase 2 (after ~22:41 ET) → Step-1 REPLACE_* template saved but Step-2 not done
                         → TradingView sends literal "REPLACE_NOW"
                         → bot rejects: WEBHOOK_INVALID
                         → TradingView shows: 409 Conflict
```

### Bot rejection log (background session)

From `terminals/538258.txt` — **31 rejections, 0 accepts**:

| Reason | Count | Detail |
|--------|------:|--------|
| `SIGNAL_STALE` | 27 | `age=21190801s` … `age=21262080s` (~245 days) |
| `WEBHOOK_INVALID` | 4 | `Invalid isoformat string: 'REPLACE_NOW'` |

`WEBHOOK_INVALID` times (ET):

- 2026-09-03 22:41 — SIGNAL_LONG
- 2026-09-03 22:56 — SIGNAL_SHORT
- 2026-09-03 23:07 — SIGNAL_LONG
- 2026-09-03 23:41 — SIGNAL_LONG

### ngrok webhook traffic (all 30 requests)

Full CSV: `forward_rehearsal/reports/2026-09-03_WEBHOOK_ATTEMPTS.csv`

| Metric | Value |
|--------|------:|
| Total POSTs | 30 |
| HTTP 409 | 30 |
| HTTP 200 | 0 |
| SIGNAL_LONG | 26 |
| SIGNAL_SHORT | 4 |
| Rejected `SIGNAL_STALE` | 15 |
| Rejected `WEBHOOK_INVALID` | 15 |

Note: Some alert fires appear as **pairs** (~1s apart) with different rejection reasons — likely two alerts (LONG+SHORT) or duplicate delivery while message was being edited.

### Shadow session verdicts (live TV)

All shadow sessions finalized with **`FORWARD_SHADOW_FAIL`** — gate failure: `no real TV alerts received`.

| Session ID | Start (UTC) | tv_signals | verdict |
|------------|-------------|----------:|---------|
| `20260903T035956Z-17deaf55` | 03:59 | 0 | FAIL |
| `20260903T040127Z-5ec231b9` | 04:01 | 0 | FAIL |
| `20260903T045154Z-8809df5c` | 04:51 | 0 | FAIL |

Reconciliation report (`SHADOW_SIGNAL_RECONCILIATION.csv`): **empty** (header only).

### Setup mistakes encountered (fixed or documented)

| Issue | Status |
|-------|--------|
| PowerShell `export` syntax | Fixed — use `$env:VAR = "..."` |
| Trailing `\` on `--use-databento\` | Fixed |
| Webhook secret set to Databento key | Fixed — separate secrets |
| `python` not on PATH | Workaround — full Python312 path |
| ngrok too old (3.3.1) | Fixed — MS Store 3.39.9 |
| Pasting `{{timenow}}` in TV message | Breaks TV JSON validator — use Add placeholder |
| `REPLACE_*` left in message | **Still open** — must complete Step 2 |
| Bot running in background vs visible terminal | User couldn't see logs — use Terminal 1 |

---

## Timeline (ET, Sep 3)

| Time | Event |
|------|-------|
| ~00:05 | Early synthetic/local-paper infra tests pass |
| ~00:51–01:34 | Shadow sessions start; webhook listening |
| ~01:34 | Long-running shadow bot + ngrok session begins |
| 02:20–22:08 | 27× TV alerts → `SIGNAL_STALE` (static Jan 1 timestamps) |
| 22:41–23:41 | 4× TV alerts → `WEBHOOK_INVALID` (`REPLACE_NOW` literal) |
| End of day | 0 valid signals; shadow gate not passed |

---

## Current configuration snapshot

| Setting | Value |
|---------|-------|
| Bot listen | `127.0.0.1:8787/webhook` |
| ngrok public URL | `https://finale-streak-bucket.ngrok-free.dev/webhook?token=…` |
| Pine hash required | `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f` |
| Symbol / timeframe | `NQ` / `1m` (not `NQ1!`) |
| Staleness limit | 120 seconds |
| Alert conditions | `P72B SIGNAL_LONG` / `P72B SIGNAL_SHORT` |
| Pine setting required | Export parity events to Data Window = **ON** |

Alert JSON templates saved locally:

- `forward_rehearsal/reports/TRADINGVIEW_ALERT_LONG.json`
- `forward_rehearsal/reports/TRADINGVIEW_ALERT_SHORT.json`

Step-1 paste templates (before Add placeholder) use `REPLACE_NOW`, `REPLACE_BAR`, `REPLACE_CLOSE`, `REPLACE_ID`.

---

## What success looks like (not seen yet today)

When the next alert is correct, expect:

**TradingView:** no 409 error

**Bot terminal:**

```
webhook valid signal_id=... event=SIGNAL_LONG
SHADOW WOULD_ENTER_LONG ...
```

**Session summary:** `tv_signals >= 1`, reconciliation row in `SHADOW_SIGNAL_RECONCILIATION.csv`

---

## Next steps (unblock)

1. **Fix both alerts** — complete Step 2 for LONG and SHORT:
   - `REPLACE_NOW` → Add placeholder → Time (UTC)
   - `REPLACE_BAR` → Time
   - `REPLACE_CLOSE` → Close
   - `REPLACE_ID` → Time (UTC)
   - One line only; no text after closing `}`
2. **Apply** only when all four replacements done
3. **Run bot in visible terminal** so you see `webhook valid` immediately
4. Wait for next P72B signal (or test alert if TV allows)
5. Optional: patch Pine to emit JSON via `alert()` + `{{alert_message}}` to avoid manual placeholders

---

## Source files referenced

| File | Contents |
|------|----------|
| `forward_rehearsal/reports/2026-09-03_WEBHOOK_ATTEMPTS.csv` | All 30 ngrok webhook attempts |
| `forward_rehearsal/sessions/2026-09-03/*/session_summary.json` | Per-session stats |
| `phase74/logs/signals.jsonl` | Synthetic test signal (valid) |
| `.cursor/projects/.../terminals/538258.txt` | Live bot rejection log |
| `.cursor/projects/.../terminals/2.txt` | ngrok status |
| `.cursor/projects/.../terminals/1.txt` | User terminal bot starts |

---

*Generated 2026-09-04 (local). Re-run ngrok inspect API or bot logs to refresh webhook attempt data.*
