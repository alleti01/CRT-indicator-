# Fix 2 — Gate Instrumentation Build Report

**Status:** Build complete — **NOT FINAL**  
**Trust label:** `PENDING_REPLAY_CONFIRMATION` (all ledger output until Sid completes TV bar-replay checklist)

---

## Part A — gate_state source replacement

### Removed
- `phase72b/python/autonomous_mirror_engine.py` and all Phase72B mirror imports from `gate_evaluator.py` and `ledger_builder.py`.

### Added

| Artifact | Purpose |
|----------|---------|
| `TV_REVIEW/phase72a_signal_ledger.pine` | Copy of frozen Layer A + **Layer D** gate instrumentation |
| `signal_ledger/gate_export.py` | Parse TradingView CSV with `GLD_*` data-window plots |
| `signal_ledger/gate_evaluator.py` | Gate state from export/alerts; cross-check; offset recompute |

### Pine Layer D (`phase72a_signal_ledger.pine`)
- **Data-window plots:** `GLD_{gate_name}` for all 14 ledger gates + `GLD_bar_time_utc_ms` (UTC ms only)
- **Pivot diagnostics:** `GLD_pivot_high_center_lag`, `GLD_pivot_low_center_lag`, `GLD_swing_period`
- **Alerts (schema 1.2):** `SIGNAL_LONG` / `SIGNAL_SHORT` JSON includes embedded `gate_state` + UTC ms timestamps only (`signal_bar_time_utc_ms`, `entry_bar_time_utc_ms`, `alert_generated_time_utc_ms`)

### Workflow
1. Load `phase72a_signal_ledger.pine` on NQ1! 1M in TradingView
2. Export chart data (CSV) → `--gate-export` input
3. Capture alert JSONL from webhook → `--signals` input (optional, for fired-bar cross-check)

---

## Part B — known_at_bar_offset recomputation

Tool: `python3 signal_ledger/tools/recompute_gate_offsets.py --gate-export <csv>`

**Fixture results** (`gate_export_sample.csv`):
- All 14 TAKE-chain gates: `known_at_bar_offset = 0` (bar-close evaluation in Pine Layer D)
- Pivot confirmation lag: **confirmed = true**, `swing_period = 5`, lag samples = `[5.0]`

Mirror-derived offsets from Phase 1 are **not** carried forward. Full-history export required for production offset CSV.

---

## Part C — hyp_R cost model

### Change
`hypothetical_outcomes.py` applies `NQ.cost_r(entry, stop)` after phase73 `build_management` + `evaluate_exit` gross R (same as `phase69.walk_trade`).

### outcome_R basis (explicit)
- **Ledger classification** uses `hyp_long_R` / `hyp_short_R` (now **net** of modeled round-trip cost).
- **Live phase73 `outcome_R` from actual fills:** phase73 records fill prices at stop/target/close but does **not** persist a separate net-R column; net realized R would be `(exit_fill - entry_fill) / risk - NQ.cost_r(entry, stop)`. The ledger does not ingest phase73 fill logs today — it uses hypothetical M0 only.
- **Not assumed:** that gross stop/target R equals realized net without cost subtraction.

### Classification impact — cost model verified (Item 2)

**Formula (exact):** `cost_R = cost_per_rt_usd / (|entry − stop| × point_value)`  
**Source:** `phase58/research/instrument.py` — `NQ.cost_per_rt_usd = 14.50` (round-turn commission+fees, no slippage model), `point_value = 20.0`, `tick_size = 0.25`.  
**Applied in:** `signal_ledger/hypothetical_outcomes.py` → `apply_m0_cost()` → `NQ.cost_r(entry, entry − risk)`.

The prior `+2.0 → ~+1.275` row used the **real computed** `NQ.cost_r`, not a rounded placeholder — but it used the **unit-test fixture** (`entry=100`, `risk=1` point), which is **not realistic NQ economics**. One point of risk makes cost **0.725R** (72.5% of a 1R stop).

#### Table A — Unit-test fixture (atr = 1 point risk) — used in `test_classify.py` only

| | hyp_long_R (gross) | cost_R | hyp_long_R (net) | threshold 1.5R | classification |
|--|-------------------|--------|------------------|----------------|----------------|
| Before cost | +2.000000 | — | — | ≥ 1.5 | `missed_reversal` |
| After cost | +2.000000 | **0.725000** | **+1.275000** | < 1.5 | `correct_pass` |

`0.725 = 14.50 / (1.0 × 20.0)` — exact, not illustrative.

#### Table B — Realistic NQ (P60-035316: entry 29584.5, ATR/risk 10.393 pts)

| | hyp_long_R (gross) | cost_R | hyp_long_R (net) | threshold 1.5R | classification |
|--|-------------------|--------|------------------|----------------|----------------|
| At gross +2.0R | +2.000000 | 0.069759 | +1.930241 | ≥ 1.5 | `missed_reversal` (unchanged) |
| At gross +1.5R | +1.500000 | 0.069759 | +1.430241 | net < 1.5 | flips to `correct_pass` |
| At gross +2.5R target | +2.500000 | 0.069759 | +2.430241 | ≥ 1.5 | `missed_reversal` (unchanged) |

`0.069759 = 14.50 / (10.392857 × 20.0)` — **~7.0% of 1R stop**, **~2.8% of 2.5R gross target**.

**Flag:** At realistic NQ risk, cost is **not** ~0.7R; the 0.725R figure is an artifact of 1-point risk in synthetic tests. Production ledger runs use live ATR → cost typically **~0.05–0.10R**. Classification counts will shift mainly near the threshold band (e.g. gross 1.5R–1.57R), not at gross 2.0R+.

---

## Layer D variable provenance (Item 1) — BLOCKING

**Standard used:** GLD plot must read the **same Layer A state variable** Layer A wrote or the **exact inline condition** at decision time — not a Layer B recompute.

### ✅ Literal same underlying Layer A state

| GLD plot | Layer D source | Layer A source | Verdict |
|----------|----------------|----------------|---------|
| `GLD_armed_long` | `gld_armed_long = p58State == 1` (L1858) | `p58State := 1` when arming (L1117) | **Same var `p58State`** |
| `GLD_armed_short` | `p58State == -1` (L1859) | L1117 SHORT arm | **Same var `p58State`** |
| `GLD_not_in_cooldown` | `not p72bCooldown` → `p58State == 3` (L1869, L1657) | Gate `p58State != 3` (L1108) | **Same var `p58State`** |
| `GLD_take_long` | `lastAction == "SIGNAL_LONG"` edge (L1871) | `lastAction := "SIGNAL_LONG"` (L1241) | **Same var `lastAction`** |
| `GLD_take_short` | `lastAction == "SIGNAL_SHORT"` edge (L1872) | L1241 SHORT | **Same var `lastAction`** |
| `GLD_bar_time_utc_ms` | `float(time)` (L1884) | Pine bar clock | **Same builtin `time`** |
| `GLD_swing_period` | `float(swingPeriod)` (L1881) | input L73 | **Same input `swingPeriod`** |

### ⚠️ RECOMPUTE — not ground truth yet (fix before Part B offsets / Part D cross-check)

| GLD plot | Layer D source | Layer A decision uses | Issue |
|----------|----------------|----------------------|-------|
| **`GLD_evidence_threshold_long`** | `p72bRawLong` (L1860) = `p58State==1 and f_p72bArmTotal("LONG")>=takeThreshold` (L1641) | Block-local `total >= takeThreshold` (L1168, L1183) | **Recomputed** via Layer B helper; Layer A `total` is not a named series. Same inputs/formula, not same variable. |
| **`GLD_evidence_threshold_short`** | `p72bRawShort` (L1861) | L1168/L1183 SHORT path | Same issue |
| **`GLD_p4_keep_long`** | `not f_p4Abstain("LONG", revSupLong, domLong)` (L1862) | `p4Abst` → **`p4Status`** (L1217–1219) | **Recomputed**; does not read Layer A `p4Status` |
| **`GLD_p4_keep_short`** | `not f_p4Abstain("SHORT", ...)` (L1863) | L1217–1219 | Same |
| **`GLD_h1_keep_long`** | `not f_h1Abstain(highSubLong, htfContraLong)` (L1864) | `h1Abst` → **`h1Status`** (L1218–1220) | **Recomputed**; does not read `h1Status` |
| **`GLD_h1_keep_short`** | `not f_h1Abstain(...)` (L1865) | L1218–1220 | Same |
| **`GLD_gate_open`** | `p72bGateOpen` (L1868, L1658) | Inline L1108 condition | **Recomputed** expression; same sub-vars (`f_posActive()`, `p58InTrade`, `p58State`, `p58BlockSignals`) |
| **`GLD_decide_e_long`** | `p72bDecE_L=="TAKE" and gld_p4_keep_long and gld_h1_keep_long` (L1866) | `decE = f_decideE(...)` → **`p58dDecision`** + separate p4/h1 (L1198–1220) | **Composite recompute**; Layer A runs `f_decideE` only on **`isNew`** path (L1186–1187); `p72bDecE_L` runs **every bar** (L1644) |
| **`GLD_decide_e_short`** | L1867 composite | L1198–1220 SHORT | Same |

### Pivot diagnostics (not ledger gates; Part B lag check only)

| GLD plot | Source | Layer A |
|----------|--------|---------|
| `GLD_pivot_high_center_lag` | `not na(pivotHigh) ? swingPeriod : na` (L1877–1879) | `pivotHigh = ta.pivothigh(...)` (L218) — **same `pivotHigh` series**, lag is **derived constant**, not a Layer A stored lag |
| `GLD_pivot_low_center_lag` | L1878–1880 | `pivotLow` L219 — same pattern |

**Blocking conclusion (superseded by Layer D patch below):** 9 of 14 named gate exports previously recomputed via Layer B. Patched in `phase72a_signal_ledger.pine` — see **Layer D patch provenance (Item 1 closed)**.

---

## Layer D patch provenance (Item 1 closed)

**Resolved gate count: 9** (not 8 — prior header was wrong). All 9 previously-flagged gates now read Layer A snapshot state.

| # | GLD plot | Layer D read (post-patch) | Layer A write / source | Same state? |
|---|----------|---------------------------|------------------------|-------------|
| 1 | `GLD_evidence_threshold_long` | L1892: `p58State==1 and gldSnapArmTotalLong>=takeThreshold` | L1180-1182: `gldSnapArmTotalLong := total` after L1179 `total = ...` | **Yes — snapshotted `total`** |
| 2 | `GLD_evidence_threshold_short` | L1893: `p58State==-1 and gldSnapArmTotalShort>=takeThreshold` | L1183-1184: `gldSnapArmTotalShort := total` | **Yes — snapshotted `total`** |
| 3 | `GLD_p4_keep_long` | L1894: `gldSnapP4KeepLong` | L1246: `gldSnapP4KeepLong := p4Status == "KEEP"` on isNew+TAKE | **Yes — reads `p4Status` at assignment** |
| 4 | `GLD_p4_keep_short` | L1895: `gldSnapP4KeepShort` | L1250: `gldSnapP4KeepShort := p4Status == "KEEP"` on isNew+TAKE | **Yes — reads `p4Status` at assignment** |
| 5 | `GLD_h1_keep_long` | L1896: `gldSnapH1KeepLong` | L1247: `gldSnapH1KeepLong := h1Status == "KEEP"` on isNew+TAKE | **Yes — reads `h1Status` at assignment** |
| 6 | `GLD_h1_keep_short` | L1897: `gldSnapH1KeepShort` | L1251: `gldSnapH1KeepShort := h1Status == "KEEP"` on isNew+TAKE | **Yes — reads `h1Status` at assignment** |
| 7 | `GLD_gate_open` | L1900: `gldSnapGateOpen` | L1119: snapshot of L1120 inline condition (export only; live branch uses inline `if`) | **Yes — snapshotted gate condition** |
| 8 | `GLD_decide_e_long` | L1898: `gldSnapDecideELong` | isNew-only updates L1219/1227/1248; **holds on non-isNew** | **Yes — isNew-gated snapshot** |
| 9 | `GLD_decide_e_short` | L1899: `gldSnapDecideEShort` | isNew-only updates L1221/1229/1252; **holds on non-isNew** | **Yes — isNew-gated snapshot** |

### decide_e_long / decide_e_short — isNew gating (explicit)

| Event | `gldSnapDecideELong` updates? | Value |
|-------|------------------------------|-------|
| isNew + decE==WAIT | **Yes** (L1219) | `false` |
| isNew + decE==PASS | **Yes** (L1227) | `false` |
| isNew + decE==TAKE | **Yes** (L1248) | `not p4Abst and not h1Abst` (after L1243-1244 set `p4Status`/`h1Status`) |
| **not isNew** (UPDATE path L1292) | **No — holds prior** | unchanged |
| Bars outside isNew block | **No — holds prior** | unchanged |

Same pattern for `gldSnapDecideEShort` at L1221/1229/1252.

**Hold on real TV chart export: ACTIVE.** Item 1 (Layer D provenance) is closed, but the combined gate for lifting the hold requires Parts B, C, and D together — see status table below. Do **not** run `ledger_builder` on real TV exports until then. TV bar-replay checklist remains open (Sid manual).

---

## Open issue 1 — gate_open regression (resolved, additive-only kept)

**Constraint:** Layer D patch must be additive export logging only — live signal branch must keep the original inline condition.

**Pine change (`phase72a_signal_ledger.pine`):**
- L1119: `gldSnapGateOpen := not f_posActive() and not p58InTrade and p58State != 3 and not p58BlockSignals` (export snapshot)
- L1120: `if not f_posActive() and not p58InTrade and p58State != 3 and not p58BlockSignals` (live branch — **not** substituted)

**Before/after comparison** (`python3 signal_ledger/diagnostics/gate_open_regression.py`):

| Window | Bars | Mismatch bars | Identical? |
|--------|------|---------------|------------|
| aug28_session | 555 | 0 | **Yes** |
| jul_aug_2026 | 58,784 | 0 | **Yes** |

Method: Phase72B mirror inline vs `gate_snap_mode` on `signal_long`, `signal_short`, `enter_long`, `enter_short`. Full artifact: `signal_ledger/reports/GATE_OPEN_REGRESSION.json`.

**Note:** Mirror proxy is **not** TradingView Pine execution. TV bar-replay remains the final confirmation path. Mirror shows bar-for-bar identical signal output for the var-gate pattern vs inline; Pine nevertheless keeps inline on the live branch to satisfy the additive-only constraint.

---

## Part B — warmup diagnosis

**Status:** **Complete** — three required checks answered in `signal_ledger/reports/PART_B_WARMUP_VERDICT.md`.

Prefix-truncation reruns (`warmup_diagnosis.py`, `PART_B_WARMUP_DIAGNOSIS.json`) are **supplementary only** — they do not close Part B by themselves.

| Check | Result (summary) |
|-------|------------------|
| 1. Variable declarations | `lastSH`/`lastSL`/`m5LastSH` = **`var`**; `m15H4`/`m15L4`/`m15C12` = **ordinary `request.security` series**. No daily/session reset in code. |
| 2. Live reload/restart | Pine runs on TV only; bot/NinjaTrader restarts do not reload Pine. Steady-state continuous chart → no recurring truncation; reload/cold-start is one-time per script/chart init. |
| 3. Shadow log correlation | **74** real/accepted signals: **0** NEUTRAL context, evidence always **5** on accepted webhooks — **no** warmup-insufficient signature in live/shadow data. |

**“5 vs 1” divergence:** **Synthetic prefix-truncation only** (bar 3136687, Aug 28 2026) — **not** shadow log data. Both totals below threshold.

**Verdict:** **(a)** for prefix tests; **not (b)** for continuous live — truncation-like NaN is cold-start/reload/insufficient-history, not live-recurring steady-state (see full verdict doc).

---

## Part C — cold-start warmup guard (complete)

**Artifact:** `signal_ledger/reports/PART_C_COLD_START_WARMUP.md`

- Bounded window: `12 × 15 + swingPeriod` (= **185** 1M bars default)
- `gldHtfWarmupReady` latched `var` — no standing per-bar HTF gate after warm
- `PASS_INSUFFICIENT_WARMUP` (`GLD_pass_reason_code=1`) only during cold-start window
- Arm-total three-state export: prov **0** cold / **1** fresh / **2** stale
- `SCRIPT_INIT` alert + `GLD_script_init_utc_ms` on reload
- **9 Layer D gates unchanged** outside cold-start window

**Part D (ledger NaN handling)** — **Implemented** — `PART_D_LEDGER_NAN_HANDLING.md`

---

## Hold / trust status

| Gate | Status |
|------|--------|
| Layer D provenance (9 gates) | **Closed** |
| gate_open additive-only + mirror regression | **Closed** (mirror identical; inline kept) |
| Part B warmup diagnosis (checks 1–3) | **Closed** — `PART_B_WARMUP_VERDICT.md` |
| Part C cold-start warmup guard | **Verified** — `PART_C_COLD_START_WARMUP.md` + `PART_C_VERIFICATION.md` |
| Part D ledger NaN handling | **Verified** (fixture + real windows) — `PART_D_LEDGER_NAN_HANDLING.md` |
| TV bar-replay checklist (Sid) | **Open** |
| **Hold on real TV export / ledger_builder** | **ACTIVE** — B+C+D fixture-complete; lift after joint sign-off + TV replay |

---

## Part D — instrumentation cross-check

`cross_check_alert_vs_export(alert_payload, export_row)` compares all 14 gates at signal bar.

**Fixture:** `alert_signal_long.json` vs `gate_export_sample.csv` bar `1704067320000` → **0 mismatches**.

Any non-empty mismatch list = instrumentation bug; do not trust aggregation.

---

## Part E — tests

```
signal_ledger/tests/ — 31/31 PASSED
```

| Test file | Coverage |
|-----------|----------|
| `test_part_d_nan_handling.py` | Nullable evidence load, tri-state, blocking_gates skip cold-start |
| `test_part_c_warmup.py` | Part C export constants |
| `test_gate_instrumentation.py` | CSV load, offsets, pivot lag, cross-check, cost hyp_R, no-lookahead |
| `test_hypothetical_m0.py` | phase73 M0 + NQ.cost_r parity |
| `test_causality.py` | Prefix invariance on export (no mirror) |
| `test_classify.py` | Classification + cost reduces missed_reversal |

---

## Reporting requirement

All outputs from `ledger_builder`, `gate_aggregate`, and `recompute_gate_offsets` print:

```
trust_status=PENDING_REPLAY_CONFIRMATION
```

**Do not treat gate rankings as causal or final** until Sid reports TV bar-replay checklist results (Aug 28 bars 3136875, 3136882, 3136894, 3136912, Aug 30 bar 3137114).

---

## Files changed

- `TV_REVIEW/phase72a_signal_ledger.pine` (new — Layer D)
- `signal_ledger/gate_export.py` (new)
- `signal_ledger/gate_evaluator.py` (rewritten)
- `signal_ledger/ledger_builder.py` (Pine export input only)
- `signal_ledger/hypothetical_outcomes.py` (phase73 + NQ.cost_r)
- `signal_ledger/signal_loader.py` (schema 1.2 + UTC ms)
- `signal_ledger/gate_aggregate.py` (trust warning)
- `signal_ledger/tools/recompute_gate_offsets.py` (new)
- `signal_ledger/tests/*` (updated + fixtures)

**Frozen unchanged:** `TV_REVIEW/phase72a_autonomous_trader.pine`
