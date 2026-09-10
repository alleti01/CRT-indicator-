# Part B — Warmup Diagnosis Verdict

**Status:** Complete (three required checks answered)  
**Prior prefix-truncation reruns:** Supplementary only — do **not** close Part B by themselves.

---

## Clarification — “5 vs 1 evidence-total divergence”

**Source:** **Synthetic prefix-truncation run only** — not shadow log data.

- Tool: `signal_ledger/diagnostics/warmup_diagnosis.py`
- Artifact: `signal_ledger/reports/PART_B_WARMUP_DIAGNOSIS.json`
- Bar: **3136687** (`2026-08-28 11:41:00` Chicago), SHORT direction
- `total_full = 5`, `total_prefix = 1` (prefix start 277 bars later than full window)
- `take_threshold = 4` → **both** `evidence_threshold_full` and `evidence_threshold_prefix` are **False** — no signal fired on either path at that bar

This confirms NaN/truncation affects computed totals in research — it is **not** live shadow evidence.

---

## Check 1 — Variable declaration (production Pine)

**File:** `TV_REVIEW/phase72a_autonomous_trader.pine` (frozen Layer A — same declarations in ledger copy)

### `lastSH`, `lastSL` — **`var`** (persist until script reload)

```220:229:TV_REVIEW/phase72a_autonomous_trader.pine
var float lastSH = na
var float lastSL = na
var float prevSH = na
var float prevSL = na
if not na(pivotHigh)
    prevSH := lastSH
    lastSH := pivotHigh
if not na(pivotLow)
    prevSL := lastSL
    lastSL := pivotLow
```

### `m5LastSH` (and paired `m5LastSL`) — **`var`**

```193:202:TV_REVIEW/phase72a_autonomous_trader.pine
var float m5LastSH = na
var float m5PrevSH = na
var float m5LastSL = na
var float m5PrevSL = na
if not na(m5PivotH)
    m5PrevSH := m5LastSH
    m5LastSH := m5PivotH
if not na(m5PivotL)
    m5PrevSL := m5LastSL
    m5LastSL := m5PivotL
```

### `m15H4`, `m15L4`, `m15C12` — **ordinary series** (recomputed each bar via `request.security`)

```205:207:TV_REVIEW/phase72a_autonomous_trader.pine
m15H4 = request.security(syminfo.tickerid, "15", high[4], lookahead=barmerge.lookahead_off)
m15L4 = request.security(syminfo.tickerid, "15", low[4], lookahead=barmerge.lookahead_off)
m15C12 = request.security(syminfo.tickerid, "15", close[12], lookahead=barmerge.lookahead_off)
```

### Implication

| Construct | Reset mechanism |
|-----------|-----------------|
| `lastSH` / `lastSL` / `m5LastSH` / `m5LastSL` | **`var`** — accumulate across bars; reset only on **Pine script reload** (save/edit, re-add indicator, new chart load). **No daily or session boundary reset in code.** |
| `m15H4` / `m15L4` / `m15C12` | Fresh `request.security()` each bar; may read **`na`** early in chart history when insufficient completed 15M bars exist in TV’s loaded range. Not `var`-held. |

A “daily/session reset” of swing state **does not exist in Pine**. Warmup gaps for `var` swing state occur at **cold start / script reload**, not at RTH open.

---

## Check 2 — Live reload / restart (TradingView + NinjaTrader bridge)

### Architecture (from repo artifacts)

| Component | Runs Pine? | Restart effect on Pine state |
|-----------|------------|------------------------------|
| **TradingView chart** (`phase72a_autonomous_trader.pine`) | **Yes** | Script reload re-executes from bar 0; **`var` resets to init** |
| **NinjaTrader bridge / phase74 webhook bot** | **No** | Receives alert JSON only; restart reloads **bot** state (`phase74/reports/EXECUTION_SAFETY_AUDIT.md`) |
| **`forward_rehearsal` shadow runner** | **No** | Documented bot restarts Sep 3 (`2026-09-03_WINDOWS_SETUP_DIGEST.md` L49: “00:59 ET and 01:58 ET”) — **Python process only** |

### Does live production reload Pine during normal operation?

**Repo evidence:** No logged TradingView script reload events during accepted-signal windows. No instrumentation captures TV indicator re-init timestamps.

**Documented normal path:** Alerts fire from a TV chart left running with frozen Phase72A (`pine_hash` in webhook payloads). Steady-state bar updates do **not** re-run script from bar 0.

**Reload triggers (operator / TV platform — not logged in repo):**

- Deliberate script **save/edit**
- Indicator **remove/re-add**, symbol/timeframe change, new chart layout
- Browser/tab refresh or TV session recovery (platform-dependent; may re-warm `var` state)

**Answer:** Under **continuous, unchanged** TV chart operation, truncation-like warmup **does not recur bar-by-bar**. The only live-relevant warmup gap is **cold-start at script/chart init** (once per reload), which for a long-running production chart is **historically distant** unless a reload occurred.

**Gap:** Operator confirmation that the production TV chart ran uninterrupted (no save/re-add) across Sep 8 shadow window is **not** in repo — inference from 22h continuous signal stream, not a reload audit log.

---

## Check 3 — Shadow log correlation (live/shadow evidence)

### Sources searched

| File | Accepted / real signals | Context field |
|------|-------------------------|---------------|
| `forward_rehearsal/reports/2026-09-08_shadow_signals.csv` | **26** | `context` column |
| `forward_rehearsal/reports/WEBHOOK_ALERTS_FULL.csv` | **48 ACCEPTED** | `context` inside `payload_json` |
| `forward_rehearsal/reports/ACCEPTED_SIGNALS_FOR_IMPROVEMENT.csv` | 12 | no context column |
| `phase74/logs/signals.jsonl` | 2 | `context` |

### Context distribution (real payloads)

| Source | BULLISH | BEARISH | NEUTRAL | Other |
|--------|---------|---------|---------|-------|
| Sep 8 shadow (26) | 12 | 14 | **0** | — |
| All accepted webhooks (48) | 24 | 24 | **0** | — |
| All webhook payloads (200) | 144 | 56 | **0** | — |

### Evidence scores (accepted webhooks)

- `evidence` in alert JSON: **always 5** (min=5, max=5, n=48)
- **0** signals with `evidence ≤ 2` or `evidence == 0`

### Warmup-insufficient pattern search

| Pattern | Found? |
|---------|--------|
| `context == NEUTRAL` on fired signals | **No** (0 / 74 real+accepted) |
| Low/zero evidence on accepted signals | **No** |
| Signal cluster only at log history start | **No** — Sep 8 first signal `2026-09-08T01:22:00Z`, last `2026-09-08T23:26:00Z` (~22h span, 26 events) |
| Correlation with bot restart + immediate misfire | **No** — `phase74/logs/errors.jsonl`: 0 restart-related errors; Sep 3 bot restarts predate Sep 8 shadow day |
| `DATA_MISSING` bars (Sep 8 digest: 115 missing vs 1127 healthy) | Present in session health — **not** correlated with NEUTRAL context or low evidence in signal payloads |

**Note:** Alert `context` reflects directional context at signal time; a NEUTRAL `ctxDir` would typically **block WATCH→ARMED** (`tradeDir == ""` at L1111), so NEUTRAL on fired alerts is structurally unlikely. Warmup damage would more likely appear as **missing** signals or **distorted scores**, not NEUTRAL alerts. Shadow logs show **neither** low evidence **nor** directional anomalies on accepted paths.

---

## Verdict — (a) vs (b)

| Question | Answer |
|----------|--------|
| **(a) Research-artifact-only?** | **Yes** for prefix-truncation / Python mirror prefix tests (`phase72a_causality/reports/PREFIX_VS_FULL_SERIES.json`, `warmup_diagnosis.py`). These simulate mid-history chart load — not observed in shadow payloads. |
| **(b) Genuinely live-recurring during continuous operation?** | **No evidence in shadow logs.** 74 real/accepted signals show BULLISH/BEARISH context and evidence=5 throughout. No NaN-derived neutral pattern, no low-evidence cluster at log start. |

### Combined Part B conclusion

**Truncation-like NaN/warmup insufficiency is a cold-start / script-reload / insufficient-chart-history phenomenon — not a recurring steady-state live failure mode** for the production path documented in `forward_rehearsal/reports/`.

**Residual live risk (not seen in shadow data):** Pine script save/re-add or chart history reload resets `var` swing state and re-enters HTF warmup — operator-dependent, not bar-by-bar.

---

## Part C / Part D gate

| Item | Status |
|------|--------|
| Part B three checks | **Complete** — this document |
| Part C (evidence_threshold NaN export fix) | **Unblocked to spec** — conditional fix targets **reload/cold-start + stale snap hold**, not ongoing live recurrence |
| Part D (ledger NaN handling) | **Unblocked to spec** after Part C |
| Hold on real TV export / `ledger_builder` | **Still ACTIVE** until Part C + Part D confirmed |

Do **not** assume (a) or (b) from prefix tests alone; this verdict rests on checks 1–3 above.
