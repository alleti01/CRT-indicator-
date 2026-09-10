# Windows Guide — Phase72A Production + Signal Ledger Validation

**Trust label:** All ledger pipeline output remains `PENDING_REPLAY_CONFIRMATION` until this checklist is completed on real TradingView bars.

**Documentation only.** This guide does not change production Pine, ledger Pine, Phase73/74, webhooks, M0, or tests.

---

## Section 1 — Purpose

There are two Pine scripts:

### 1. Production

**File:** `TV_REVIEW/phase72a_autonomous_trader.pine`

**Frozen SHA256:**

`d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f`

(Frozen metadata also recorded in `phase73/config/PINE_SIGNAL_FREEZE.json` and `phase73/reports/PINE_SIGNAL_AUTHORITY.md`.)

**Role:**

- actual Phase72A signal authority
- produces the signals used by shadow trading
- production webhook owner
- **MUST remain frozen** — do not edit for validation

### 2. Diagnostic ledger

**File:** `TV_REVIEW/phase72a_signal_ledger.pine`

**Role:**

- diagnostic copy of Layer A + Layer D gate instrumentation
- exposes internal `GLD_*` gate states in the TradingView Data Window
- supports TradingView chart-data export
- supports gate-state validation and ledger analysis
- **NOT** the production trading authority

### Why run both (temporarily)

Running both simultaneously is **temporary validation**.

The goal is to prove on **actual TradingView bars**:

```text
PRODUCTION SIGNALS = LEDGER SIGNALS
```

Compare: same timestamp, same direction, same TAKE/entry event.

Once proven, there is **no requirement** to permanently run both scripts.

---

## Section 2 — Final architecture

### Normal production

```text
TradingView
    ↓
Phase72A Production  (TV_REVIEW/phase72a_autonomous_trader.pine)
    ↓
Webhook
    ↓
Python  (Phase73 / Phase74 shadow stack)
    ↑
NinjaTrader live data  (Phase74 bar bridge)
    ↓
Shadow / eventual execution
```

Shadow startup scripts in this repo (reference only — do not modify for this validation):

- `scripts/start-ninjatrader-shadow.ps1`
- `scripts/start-ninjatrader-validation.ps1`

### Diagnostic workflow

```text
TradingView
    ↓
Phase72A Signal Ledger  (TV_REVIEW/phase72a_signal_ledger.pine)
    ↓
GLD_* gate states  (Data Window plots)
    ↓
TradingView CSV export
    ↓
Python ledger analysis  (signal_ledger/)
```

### Temporary validation (this guide)

```text
              SAME NQ 1M BARS
                    │
           ┌────────┴────────┐
           ↓                 ↓
     Production Pine     Ledger Pine
           │                 │
       LONG/SHORT         LONG/SHORT
           │                 │
           └──── COMPARE ────┘
```

**Required match:**

- same timestamp
- same direction
- same TAKE / entry event

---

## Section 3 — Windows pre-check

Before opening TradingView:

### 1. Pull latest repository

```powershell
cd <PATH_TO_REPO>
git status
git pull
```

Replace `<PATH_TO_REPO>` with your local clone path. This repo does not ship a fixed Windows install path.

### 2. Confirm Pine files exist

```powershell
Test-Path ".\TV_REVIEW\phase72a_autonomous_trader.pine"
Test-Path ".\TV_REVIEW\phase72a_signal_ledger.pine"
```

Both must return `True`.

### 3. Verify production Pine SHA256

```powershell
Get-FileHash ".\TV_REVIEW\phase72a_autonomous_trader.pine" -Algorithm SHA256
```

**Expected hash:**

`d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f`

If it does **not** match: **STOP.** Do not continue validation until the discrepancy is understood.

### 4. Python environment

**VERIFY_ON_WINDOWS:** Confirm Python 3 is available and repo dependencies are installed.

```powershell
python --version
```

If `python` is not found, try `py --version` or `python3 --version`.

Run ledger tests (optional sanity check before TV work):

```powershell
python -m pytest signal_ledger/tests/ -q
```

Expected: all tests pass (fixture-level; not a substitute for TV validation).

---

## Section 4 — TradingView setup

**Recommended:** two-chart layout.

| Chart | Script |
|-------|--------|
| **Chart A** | Phase72A **Production** |
| **Chart B** | Phase72A **Signal Ledger** |

Set **both** charts to:

- exact same NQ instrument (typically `NQ1!` continuous — match what shadow uses)
- exact same contract/symbol series
- **1-minute** timeframe
- same session settings
- same chart type (candles recommended)
- same relevant Pine inputs (see Sections 5–6)

**Warning:** Do not compare `NQ1!` against a different individual contract unless that difference is intentional. Both charts must use the **same underlying TradingView data series** for this parity test.

Link crosshairs / sync time axis if your TradingView layout supports it.

---

## Section 5 — Chart A: Production

### Load

Copy/paste or open from repo:

`TV_REVIEW/phase72a_autonomous_trader.pine`

This is **production**. Do not edit its code on the Windows machine.

### Settings

Keep normal production display settings (`Show TAKE`, `Show ENTRY`, etc. as you use for shadow).

**Input group `Display` (representative inputs):**

- `Show TAKE`
- `Show ENTRY`
- `Show stop/target`
- `Show exits`
- (others off unless you normally use them)

**Phase72B parity export (optional, usually OFF on production chart):**

- `Export parity events to Data Window` (`exportParity`) — default **false** in source

### Webhook

This chart is allowed to own the existing **shadow webhook**.

Do **NOT**:

- edit production Pine logic
- change entry logic
- enable experimental settings for validation
- add diagnostic modifications
- recreate logic manually in a new script

### Record

Write down the production indicator settings you used (screenshot or notes): symbol, timeframe, session, and any non-default inputs.

---

## Section 6 — Chart B: Ledger

### Load

`TV_REVIEW/phase72a_signal_ledger.pine`

### Identify the script

The ledger source currently declares:

```pine
indicator("Phase72A Autonomous Trader", ...)
```

— the **same title** as production. In TradingView, distinguish Chart B by filename / saved script name.

**Cosmetic only:** You may rename the indicator title in the Pine Editor to e.g. `"Phase72A Signal Ledger"` for clarity. This must **not** alter any logic.

### Required ledger inputs

**Input group:** `Signal Ledger Gate Export (Layer D — diagnostic only)`

| Input name in Pine | Recommended for validation |
|--------------------|----------------------------|
| `Export gate booleans to Data Window (GLD_*)` (`enableGateLedgerExport`) | **ON** |
| `Fire SIGNAL alerts with gate_state JSON (UTC only)` (`enableGateLedgerAlerts`) | **OFF** initially |
| `Frozen Layer A SHA256` (`gldPineHash`) | leave default (`d75ff747…`) |

### Display inputs (reduce clutter)

**Input group `Display`:** turn **OFF** unless needed:

- `Show WAIT`, `Show PASS`, `Show P4 abstains`, `Show H1 abstains`, `Show HTF context table`, `Show diagnostic table`, `Show reason codes`, `Show Phase58K extension diagnostic`

Keep `Show TAKE` / `Show ENTRY` **ON** if you need visual signal parity vs Chart A.

**Optional:** `Export parity events to Data Window` (`exportParity`) — only if you also want `P72B_*` columns alongside `GLD_*` (not required for gate ledger validation).

### Do NOT

Route ledger alerts to the production trading webhook during initial validation (Section 7).

---

## Section 7 — Why ledger alerts are OFF

If both scripts send the same LONG/SHORT event to the production webhook, Python may receive **duplicate** events.

Therefore during parity validation:

| Script | Role |
|--------|------|
| **Production** | webhook owner |
| **Ledger** | diagnostic / export tool |

If ledger JSON alerts are tested later (Section 14), they must go to:

- a separate diagnostic endpoint, **or**
- a separate log file

**NOT** the live/shadow trading webhook (`scripts/start-ninjatrader-shadow.ps1` uses `http://127.0.0.1:8787/webhook` — **VERIFY_ON_WINDOWS** for your configured URL/secret).

---

## Section 8 — Data Window check

On **Chart B**, open TradingView **Data Window**. Hover over several confirmed bars.

Confirm plots whose **names begin with `GLD_`** are visible.

### Actual `GLD_*` plot names (from ledger Pine source)

These are the real Data Window column names — there are **no** `GLD_context`, `GLD_location`, etc. in the current ledger script:

**TAKE-chain gates:**

- `GLD_armed_long`
- `GLD_armed_short`
- `GLD_evidence_threshold_long`
- `GLD_evidence_threshold_short`
- `GLD_decide_e_long`
- `GLD_decide_e_short`
- `GLD_p4_keep_long`
- `GLD_p4_keep_short`
- `GLD_h1_keep_long`
- `GLD_h1_keep_short`
- `GLD_gate_open`
- `GLD_not_in_cooldown`
- `GLD_take_long`
- `GLD_take_short`

**Part C / warmup / arm-total:**

- `GLD_htf_warmup_ready`
- `GLD_arm_total_long`
- `GLD_arm_total_short`
- `GLD_arm_total_long_prov`
- `GLD_arm_total_short_prov`
- `GLD_pass_reason_code`
- `GLD_script_init_utc_ms`

**Timestamps / pivot diagnostics:**

- `GLD_bar_time_utc_ms`
- `GLD_pivot_high_center_lag`
- `GLD_pivot_low_center_lag`
- `GLD_swing_period`

### Checks

- `1` / `0` (or true/false) states appear on warm bars
- `GLD_evidence_threshold_*` may show **NaN** only during cold-start bars (historical prefix — unlikely on recent live bars)
- values change across bars; not all NaN on recent session bars
- timestamp/bar corresponds to the bar under the crosshair

If **`GLD_*` fields are absent:** **STOP.** Do not export or run Python analysis until ledger configuration is fixed (`enableGateLedgerExport = ON`, script saved/applied, chart refreshed).

---

## Section 9 — Production ↔ Ledger signal parity

This is the main reason both scripts run temporarily.

Observe **actual** TAKE signals on both charts (labels and/or Data Window `GLD_take_*` / production `P72B_signal*` if `exportParity` enabled).

### Manual comparison table

| EVENT # | PRODUCTION TIME (UTC or NY — be consistent) | PRODUCTION DIRECTION | LEDGER TIME | LEDGER DIRECTION | MATCH? |
|---------|-----------------------------------------------|----------------------|-------------|------------------|--------|
| 1 | (example) 14:31 | LONG | 14:31 | LONG | PASS |
| 2 | (example) 15:07 | SHORT | 15:07 | SHORT | PASS |

**Do not** treat example timestamps as expected events.

### Minimum sample

- at least **5 LONG** and **5 SHORT** if available
- better: **20 total** events

### Required

- Production signal time = Ledger signal time (same 1M bar)
- Production direction = Ledger direction
- No unexplained **extra** ledger signal
- No unexplained **missing** ledger signal

### If mismatch

**STOP.** Record:

- timestamp
- direction
- chart screenshots (both charts, same bar)
- Pine inputs on both charts
- symbol and timeframe

Do **NOT** change strategy logic to force parity.

---

## Section 10 — Event ID parity

### Ledger

When `enableGateLedgerAlerts` is ON, SIGNAL alerts include JSON with:

- `event_id` (format from `f_gld_event_id`: `{ticker}_{DIR}_{yyyyMMdd'T'HHmmss'Z'}_TAKE`)
- `direction`
- `signal_bar_time_utc_ms`
- embedded `gate_state`

Fixture example: `signal_ledger/tests/fixtures/alert_signal_long.json`

### Production

`TV_REVIEW/phase72a_autonomous_trader.pine` does **not** currently expose `event_id` in alert JSON (production uses `alertcondition` tied to `exportParity`, not dynamic `alert()` payloads).

**For initial validation:** use **timestamp + direction** as the parity key on Chart A vs Chart B.

Do **not** fabricate an event ID after the fact and call it Pine ground truth.

If/when production gains structured alert IDs, add event-ID comparison as an additional gate.

---

## Section 11 — Bar Replay causality check

**Mandatory** before trusting ledger gate values.

Use **Chart B (ledger)**. Open TradingView **Bar Replay**.

Select at least **5** known regions, mixed:

- LONG TAKE region
- SHORT TAKE region
- reversal-looking region
- swing/pivot region
- quiet/choppy region

Step forward **one 1M bar at a time**.

Watch:

- `GLD_*` gate values
- `GLD_take_long` / `GLD_take_short`
- `GLD_pivot_*_center_lag` / `GLD_swing_period`

### Question

Does any **live decision gate** appear on an earlier bar **only after** future bars arrive (backdating)?

**Valid example** (pivot confirmation lag = `swingPeriod`, default 5):

```text
10:30  potential pivot center
10:31 … 10:34  right-side bars forming
10:35  pivot confirmation causally available
```

Gate may first become meaningful at **10:35**.

**Invalid:**

Nothing visible at 10:30 during replay, but after reaching 10:35 the **final** chart makes a gate look as if it was known at 10:30.

### If invalid behavior affects a TAKE-chain gate

**STOP.** Record:

- gate name (`GLD_*` plot name)
- pivot/origin bar time
- confirmation bar time
- first causally visible bar during replay
- what the non-replay chart shows

Reference repo audit tooling (offline, not TV): `phase72a_causality/diagnostics/replay_gate_causality.py` — **supporting research only**, not a substitute for this TV Bar Replay step.

---

## Section 12 — Real TradingView CSV export

After Data Window and Bar Replay checks pass:

1. Use **Chart B (ledger)** only.
2. Export TradingView chart data (CSV).
3. Save with a clear name, e.g.:

   `phase72a_ledger_tv_export_2026-09-10.csv`

4. Do **not** overwrite older exports.

### Confirm CSV contents

Open the CSV in a text editor or Excel. Verify columns exist for:

- time / timestamp
- OHLC (if TradingView included them)
- **`GLD_*`** columns listed in Section 8

### IMPORTANT

This must be a **real TradingView export**.

Do **NOT** substitute for this validation step:

- Phase72B mirror CSVs (`signal_ledger/reports/diagnostics/mirror_gld_export_*.csv`)
- synthetic fixtures (`signal_ledger/tests/fixtures/gate_export_*.csv`)
- Python-generated gate values

---

## Section 13 — Real export analysis

Run from **repository root** in PowerShell. Use `python` — if that fails, try `py` (**VERIFY_ON_WINDOWS**).

### Step 1 — Parse gate export (smoke test)

Confirms real `GLD_*` columns load and pivot lag metadata is readable:

```powershell
python signal_ledger/tools/recompute_gate_offsets.py `
  --gate-export ".\path\to\phase72a_ledger_tv_export_<DATE>.csv" `
  --out-csv ".\signal_ledger\output\GATE_KNOWN_AT_OFFSETS.csv" `
  --out-json ".\signal_ledger\output\PIVOT_LAG_CHECK.json"
```

Expected stdout includes `trust_status=PENDING_REPLAY_CONFIRMATION`.

### Step 2 — Part D tri-state / cold-start check on real CSV

There is **no single dedicated CLI** for Part D on a real TV file. Use the repo’s Python modules directly:

```powershell
python -c @"
from pathlib import Path
import pandas as pd
from signal_ledger.gate_export import load_tv_gate_export
from signal_ledger.gate_tri_state import evidence_threshold_state, gate_state_detail_from_export_row

path = Path(r'.\path\to\phase72a_ledger_tv_export_<DATE>.csv')
df = load_tv_gate_export(path)
cold = 0
for _, row in df.iterrows():
    d = gate_state_detail_from_export_row(row)
    states = {d['evidence_threshold_long_state'], d['evidence_threshold_short_state'],
              d['arm_total_long_state'], d['arm_total_short_state']}
    if 'insufficient_warmup' in states:
        cold += 1
print('bars_total', len(df))
print('bars_any_insufficient_warmup', cold)
print('bars_pass_reason_code_1', int((df.get('pass_reason_code', pd.Series(dtype=float)) == 1).sum()))
print('bars_htf_warmup_ready_false', int((df.get('htf_warmup_ready', pd.Series(dtype=bool)) == False).sum()))
"@
```

**Expected on recent live/session bars:** `bars_any_insufficient_warmup = 0` (matches Part C finding: cold-start confined to bar_index 0–184, not recent NQ bars). If non-zero on **recent** bars, **STOP** and investigate before trusting the ledger.

### Step 3 — Ledger builder (full pipeline)

**Requires** local NQ 1M research data via `phase58j.research.lw_data.load_markets_lw()` — **VERIFY_ON_WINDOWS** that this data exists on the Windows machine.

```powershell
python signal_ledger/ledger_builder.py `
  --start 2026-08-28 `
  --end 2026-08-28 `
  --gate-export ".\path\to\phase72a_ledger_tv_export_<DATE>.csv" `
  --output ".\signal_ledger\output\signal_quality_ledger.parquet" `
  --threshold-r 1.5
```

Optional: attach shadow signal logs for `event_id` merge:

```powershell
python signal_ledger/ledger_builder.py `
  --start 2026-08-28 `
  --end 2026-08-28 `
  --gate-export ".\path\to\phase72a_ledger_tv_export_<DATE>.csv" `
  --signals ".\phase74\logs\<VERIFY_ON_WINDOWS>.jsonl" `
  --output ".\signal_ledger\output\signal_quality_ledger.parquet"
```

Expected stdout includes `trust_status=PENDING_REPLAY_CONFIRMATION (all rows)`.

### Step 4 — Gate aggregation (after ledger built)

```powershell
python signal_ledger/gate_aggregate.py `
  --ledger ".\signal_ledger\output\signal_quality_ledger.parquet"
```

### What NOT to run as TV ground truth

| Script | Role |
|--------|------|
| `signal_ledger/diagnostics/part_c_verification.py` | Mirror-based Part C proof |
| `signal_ledger/diagnostics/part_d_real_window_verification.py` | Mirror-synthesized export only |
| `signal_ledger/diagnostics/gate_open_regression.py` | Mirror regression |
| `phase72b/` tools | Phase72B mirror — **not** TV ground truth |

### Repo reference docs

- `signal_ledger/README.md`
- `signal_ledger/reports/PART_D_LEDGER_NAN_HANDLING.md`
- `signal_ledger/reports/FIX2_GATE_INSTRUMENTATION.md`

---

## Section 14 — Alert payload ↔ export parity

When ledger JSON alerts are **intentionally** tested:

1. Turn `Fire SIGNAL alerts with gate_state JSON` **ON** on Chart B.
2. Route alerts to a **diagnostic** destination only — **NOT** production webhook.
3. For each fired SIGNAL, compare:

| Alert JSON field | Export check |
|------------------|--------------|
| `event_id` | same bar / same signal |
| `direction` | matches `GLD_take_*` |
| `signal_bar_time_utc_ms` | matches `GLD_bar_time_utc_ms` on that bar |
| each key in `gate_state` | matches corresponding `GLD_*` column on same bar |

Cross-check logic in repo: `signal_ledger/gate_evaluator.py` → `cross_check_alert_vs_export()`.

Fixture test: `signal_ledger/tests/test_gate_instrumentation.py` (fixture CSV + JSON — not your TV export).

If **any** disagreement on the same bar: **STOP.** Instrumentation is not yet ground truth.

---

## Section 15 — Phase72B warning

> **PHASE72B IS NOT PHASE72A GROUND TRUTH.**
>
> Phase72B is an independent Python reimplementation.
>
> Historical status: **`PHASE72B_MANUAL_PARITY_LIMIT_REACHED`**  
> (see `phase73/reports/PINE_SIGNAL_AUTHORITY.md`, `phase73/config/PINE_SIGNAL_FREEZE.json`)
>
> Phase72B may be used for:
> - synthetic fixtures
> - supporting diagnostics
> - development tests
>
> Phase72B must **NOT** be used to override or replace:
> - real Phase72A Pine state
> - real TradingView gate exports
> - real TradingView event timing

---

## Section 16 — Cold start

The ledger includes **bounded cold-start handling** (Part C).

**Approximate warmup window:** **185 bars** (default)

Derived from ledger Pine:

```pine
gldHtfWarmupMinBars = 12 * 15 + swingPeriod   // swingPeriod default 5 → 185
```

TradingView normally recalculates across full loaded history before reaching the live edge, so cold-start is **not expected** to affect normal recent live signals on NQ1! (repo finding: 0/2918 signal bars in cold window on mirror bar_index audit — **must be confirmed on your real TV export**).

During cold-start:

- `GLD_pass_reason_code = 1`
- `GLD_evidence_threshold_*` may export **NaN**
- `GLD_arm_total_*_prov = 0`

Part D Python ingestion treats these as **`insufficient_warmup`** — not silent `False`.

Do **not** silently classify cold-start / NaN bars as `correct_pass` in manual review.

---

## Section 17 — Do not touch M0

This validation does **not** authorize any management changes.

**Frozen M0 (signal_ledger/config.py research constants — production management is Phase73):**

| Parameter | Value |
|-----------|-------|
| STOP | 1.0R |
| TARGET | 2.5R |
| MAX HOLD | 60 minutes |
| COLLISION | STOP_FIRST |

Do **not** add ATM, breakeven, trails, runners, partials, or dynamic management as part of this checklist.

Do **not** assume Phase71 is canonical M0 without tracing the **actual frozen Phase73** production management implementation used by shadow/live stack.

---

## Section 18 — Pass criteria

- [ ] Production Pine SHA256 correct
- [ ] Same TV symbol on both charts
- [ ] Same 1M timeframe
- [ ] Same session settings
- [ ] Same Pine inputs (recorded)
- [ ] `GLD_*` visible in Data Window (Section 8 names)
- [ ] Production / ledger LONG signals match
- [ ] Production / ledger SHORT signals match
- [ ] No unexplained extra/missing ledger signals
- [ ] Bar Replay shows no decision-gate backdating
- [ ] Real TradingView CSV exported (not mirror/fixture)
- [ ] `GLD_*` columns present in CSV
- [ ] Real CSV accepted by `recompute_gate_offsets.py`
- [ ] Part D tri-state check run on real CSV (Section 13 Step 2)
- [ ] Cold-start behavior verified on real export (recent bars: zero `insufficient_warmup` expected)
- [ ] Alert gate states match exported gate states (if alert test performed)
- [ ] Phase72B not used as ground truth
- [ ] Production Pine remained unchanged
- [ ] Production webhook remained owned by production script only

When all items pass, document **PASS** with date, symbol, session window, CSV filename, and sign-off name. That completes the TV bar-replay gate for lifting the real-export hold described in `signal_ledger/reports/PART_D_LEDGER_NAN_HANDLING.md`.

---

## Section 19 — Failure policy

If anything fails, do **NOT**:

- optimize
- change thresholds
- modify entries
- modify M0
- add filters
- “fix” the chart to look better

Instead record:

| Field | Value |
|-------|-------|
| WHAT FAILED | |
| TIMESTAMP | |
| SYMBOL | |
| TIMEFRAME | |
| INPUT SETTINGS | |
| EXPECTED | |
| OBSERVED | |
| SCREENSHOT / CSV | |
| RELEVANT EVENT ID (if any) | |

Then investigate the instrumentation/parity problem.

---

## Section 20 — After validation

Once production ↔ ledger parity and TradingView causality are confirmed, there is **no requirement** to keep both scripts running continuously.

**Normal production:**

```text
Phase72A Production → webhook → Python → NinjaTrader data → shadow
```

**Load ledger only when needed for:**

- gate analysis
- false-positive analysis
- missed-reversal analysis
- TradingView exports
- diagnostic Bar Replay

---

## Section 21 — Quick Start

1. `git pull`
2. Verify production Pine hash (`Get-FileHash`)
3. Open TradingView two-chart layout
4. Same NQ + 1M on both charts
5. Chart A = `phase72a_autonomous_trader.pine` (production)
6. Chart B = `phase72a_signal_ledger.pine` (ledger)
7. Production owns webhook
8. Ledger alerts **OFF** initially
9. `Export gate booleans to Data Window (GLD_*)` **ON**
10. Compare production vs ledger signals (≥20 events if possible)
11. Bar Replay ≥5 regions on ledger chart
12. Export ledger CSV (real TV export)
13. Run Section 13 Python checks on real CSV
14. Document PASS/FAIL (Section 18)
15. Return to production-only after validation

---

**CREATED:** `docs/WINDOWS_PHASE72A_LEDGER_VALIDATION.md`  
**PRODUCTION CODE MODIFIED:** NO  
**DOCUMENTATION ONLY:** YES
