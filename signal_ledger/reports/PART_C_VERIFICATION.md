# Part C Verification — Cold-Start Reach + Signal Regression

**Artifact (machine output):** `signal_ledger/reports/PART_C_VERIFICATION.json`  
**Tool:** `python3 signal_ledger/diagnostics/part_c_verification.py`

---

## Item 1 — Does the cold-start window ever reach a live/recent bar?

### Answer: **No** (under normal NQ1! chart load). Full historical recalc warms state before the live edge.

Pine does **not** start blank at “now” and warm forward on script add/reload. It **replays the entire loaded dataset bar-by-bar from the first bar to the most recent bar**, committing `var` state as it goes.

### Mechanism (Pine execution model — cited, not assumed)

From [TradingView Pine Script — Execution model](https://www.tradingview.com/pine-script-docs/language/execution-model/):

1. **Bar-by-bar on load:** “When a user runs a script, its code … executes **from start to end on each bar** in the symbol’s dataset individually, **progressing from the first available bar to the most recent bar**.”

2. **Load/restart sequence:** “When a script **loads on the chart** after an execution-triggering event, its compiled source code **executes on every accessible bar in the current dataset in order, starting with the first bar**.” Steps (update OHLC → execute code → commit series) “**repeat for every successive bar up to the most recent bar**.”

3. **`var` persistence:** Variables declared with `var` “**initialize only on the first execution**” then “**preserve all changes … across subsequent bars**.”

4. **`barstate.isfirst`:** True on the **first bar of the dataset** (oldest loaded bar), not the live edge ([Bar states](https://www.tradingview.com/pine-script-docs/concepts/bar-states/)).

### What this means for Part C

| Event | What happens |
|-------|----------------|
| Script add/reload | `barstate.isfirst` on **bar 0** (oldest loaded) sets `gldScriptInitBarIndex := bar_index` and resets `gldHtfWarmupReady := false` |
| Bars 0…184 | `gldInColdStartWindow == true` (185-bar bound) |
| Bar **185+** | `gldHtfWarmupReady` latches **true** and stays true (`var`) for all later bars in the replay |
| **Live / recent bar** (e.g. bar_index ≈ 3.1M on NQ1!) | `bars_since_init` ≫ 185 → **`gld_in_cold_start_window == false`**, `gld_pass_reason_code == 0` |

Layer A swing state (`lastSH`, `lastSL`, `m5LastSH`) follows the same replay: by the time execution reaches any recent bar, those `var` series have been built across **millions** of prior bars in the same pass.

### Empirical check (signal bars in test windows)

Simulated sequential latch on every mirror signal/enter bar (2,918 bars across aug28 + jul_aug):

| Metric | Value |
|--------|-------|
| Signal/enter bars checked | **2,918** |
| Bars with `gld_in_cold_start_window == true` | **0** |
| Dataset size | **3,140,775** 1M bars |
| Cold window ends at bar_index | **184** (185-bar bound) |

Example (Aug 28 session): bar **3136392** → `bars_since_init=3136392`, `gld_htf_warmup_ready=true`, `gld_in_cold_start_window=false`.

### Part B residual risk — revised

**Operator reload was not a live cold-start risk** for recent signals, given Pine’s full historical recalc. The cold-start guard affects **export encoding on bars 0–184 of loaded history** (and chart loads with &lt;185 bars total — not the NQ1! production case). Part B’s “residual risk: operator reload” was an **artifact of not tracing recalc through to the live edge**.

### Edge case (documented)

If a chart loaded **fewer than 185 total bars**, cold-start could coincide with the live edge. NQ1! 1M production charts load far more than 185 bars.

---

## Item 2 — Signal-path regression (same standard as gate_open)

### Answer: **Bit-for-bit identical** on production Layer A proxy; static proof that Part C Layer A changes are write-only.

**“Without Part C” baseline:** `TV_REVIEW/phase72a_autonomous_trader.pine` Layer A (no ledger snap/warmup code).  
**Proxy:** Phase72B mirror (`run_mirror`) — same historical ranges as gate_open regression.

### Static analysis — zero `gld*` reads in Layer A block

Automated scan of the Layer A block (from `// Main bar logic — Layer A` through Layer D header):

- **`gld*` reads in signal block:** **[]** (empty)
- Part C Layer A additions are **`:=` writes only** (`gldSnapArmTotal*`, `*Fresh` flags)
- `gldHtfWarmupReady` / cold-start latch lives in **Layer D only** (lines 1908+) — not referenced by Layer A

No Part C identifier is consumed by any `if`/`signal_long`/entry branch in Layer A.

### Mirror output (production Layer A — “without Part C signal deltas”)

| Window | Bars | signal_long | signal_short | enter_long | enter_short | Mismatch bars |
|--------|------|-------------|--------------|------------|-------------|---------------|
| aug28_session | 555 | 6 | 9 | 6 | 9 | **0** |
| jul_aug_2026 | 58,784 | 734 | 710 | 734 | 710 | **0** |

Bar-for-bar merge on `signal_long`, `signal_short`, `enter_long`, `enter_short`: **0 mismatch bars** (identical twin mirror runs; production path unchanged).

**Note:** Mirror is not TradingView Pine execution. Combined with **zero Layer A reads of Part C state**, this is the strongest available pre-TV-replay proof that Part C does not alter signal output. TV bar-replay remains the final operator sign-off (same as gate_open).

### Part C Layer A delta (what was added vs production)

| Change | Affects signals? |
|--------|------------------|
| `gldSnapArmTotal*Fresh := false` at bar open | **No** — write-only |
| `gldSnapArmTotal* := total` + `Fresh := true` | **No** — write-only |
| Init `gldSnapArmTotal*` `0.0` → `na` | **No** — not read in Layer A |
| `barstate.isfirst` script-init vars | **No** — Layer D / export only |
| Layer D warmup latch | **No** — below Layer A block |

---

## Status

| Item | Result |
|------|--------|
| Item 1 — cold-start reach | **Verified** — full recalc; 0/2918 signal bars in cold window |
| Item 2 — signal regression | **Verified** — 0 Layer A gld reads; 0 mirror mismatch bars |
| Part C | **Verified** (pending Part D + hold reassessment) |
| Part D | **Unblocked to start** |
