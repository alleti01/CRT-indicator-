# Part D — Ledger Three-State NaN Handling

**Status:** Verified (fixture + real-window mirror synthesis; real TV export still under hold).

**Trust label:** `PENDING_REPLAY_CONFIRMATION` until Sid completes TV bar-replay checklist.

---

## Problem

Part C exports `GLD_evidence_threshold_*` as **`na`** during cold-start (not misleading `0`). The ledger loader previously used `_as_bool` with `fillna(0)`, silently treating unknown as **fail**. That corrupts blocking-gate analysis and cross-checks.

Part D fixes Python ingestion to preserve three distinct states:

| State | Pine signal | Ledger interpretation |
|-------|-------------|----------------------|
| **Pass / fail (warm)** | Explicit `1` / `0` export | `evidence_threshold_*_state` = `pass` / `fail` |
| **Insufficient warmup** | `na` export + `pass_reason_code=1` or `arm_total_*_prov=0` | `insufficient_warmup` — **not** a block |
| **Stale hold** | `arm_total_*_prov=2` | `stale_hold` on arm total; threshold bool still read if exported |
| **Unknown na** | `na` without cold markers | `unknown_na` — excluded from blocking list |

---

## Code changes

| File | Change |
|------|--------|
| `signal_ledger/config.py` | `NULLABLE_GATE_NAMES` for evidence gates |
| `signal_ledger/gate_export.py` | `_as_bool_nullable()` — preserves `na` on evidence columns |
| `signal_ledger/gate_tri_state.py` | **New** — `arm_total_state`, `evidence_threshold_state`, `gate_state_detail_from_export_row`, `blocking_gates_for_direction` |
| `signal_ledger/gate_evaluator.py` | Re-exports tri-state helpers; cross-check allows both-null evidence |
| `signal_ledger/ledger_builder.py` | Adds `gate_state_detail`, `blocking_gates`, `*_state` columns |
| `signal_ledger/signal_loader.py` | Preserves `null` evidence in alert `gate_state` JSON |

---

## Ledger row schema (additions)

- `gate_state_detail` — JSON with tri-state fields + optional Part C numerics
- `blocking_gates` — JSON list; **skips** evidence when `insufficient_warmup` / `unknown_na`
- `evidence_threshold_long_state` / `evidence_threshold_short_state`
- `arm_total_long_state` / `arm_total_short_state`

`gate_state` JSON retains nullable booleans (`null` = unknown, not false).

---

## Verification (fixture-level)

| Check | Result |
|-------|--------|
| Cold-start CSV: evidence export empty → parsed `na` | **Pass** |
| `gate_state_from_export_row`: evidence = `None` not `False` | **Pass** |
| `evidence_threshold_state` → `insufficient_warmup` when `pass_reason=1` | **Pass** |
| `blocking_gates`: evidence omitted during cold-start | **Pass** |
| Warm sample: explicit fail still blocks | **Pass** |
| Existing gate instrumentation tests | **Pass** (22 + Part D tests) |

Fixture: `signal_ledger/tests/fixtures/gate_export_cold_start.csv`

---

## Verification (real analysis windows — aug28 + jul_aug)

**Tool:** `python3 signal_ledger/diagnostics/part_d_real_window_verification.py`  
**Artifact:** `signal_ledger/reports/PART_D_REAL_WINDOW_VERIFICATION.json`

No TV GLD chart CSV exists in-repo for these windows. Verification uses the **same NQ LW dataset and window bounds** as Parts B/C: mirror bars → Part C export encoding synthesis → `load_tv_gate_export` → `gate_tri_state`. Same caveat as Part C (mirror ≠ TV Pine).

### `insufficient_warmup` counts (tri-state after Part D ingestion)

| Window | Bars | `pass_reason_code=1` | `htf_warmup_ready=false` | Any `insufficient_warmup` state | bar_index range |
|--------|------|----------------------|----------------------------|--------------------------------|-----------------|
| **aug28_session** | 555 | **0** | **0** | **0** | 3,136,391 – 3,136,945 |
| **jul_aug_2026** | 58,784 | **0** | **0** | **0** | 3,078,162 – 3,136,945 |

All window bars have `bar_index` ≫ 185 (`bars_below_warmup_min_in_window = 0` for both). **Zero** bars receive cold-start encoding (`pass_reason=1`, warmup not ready, or tri-state `insufficient_warmup`). This **matches Part C Item 1**: cold-start is confined to bar_index 0–184 on full-history recalc and never reaches recent/live bars in the NQ1! production case.

### Negative control (prefix bars 0–199)

| Metric | Value |
|--------|-------|
| Bars synthesized | 199 |
| `insufficient_warmup` flagged | **185** (bars 0–184) |
| Expected cold window | 185 |

Confirms Part D ingestion **does** flag cold-start when present — the real-window zero is absence of cold bars, not a parser blind spot.

### prov=0 disambiguation (warm unset snap)

Pine overloads `arm_total_*_prov=0` for (a) cold-start and (b) warm bars before first snap assignment on that side. Part D disambiguates via `pass_reason_code` + `htf_warmup_ready`: only (a) maps to `insufficient_warmup`; (b) maps to `unset` and does not block TAKE analysis.

Synthesized export CSVs (reproducible): `signal_ledger/reports/diagnostics/mirror_gld_export_{aug28_session,jul_aug_2026}.csv`

---

## Hold status (combined B + C + D)

| Part | Status |
|------|--------|
| B — warmup diagnosis | ✅ Verified |
| C — cold-start guard | ✅ Verified |
| D — ledger NaN handling | ✅ Verified (fixture + real-window mirror synthesis) |
| **Real TV export / `ledger_builder`** | 🔒 **Hold remains** until joint B+C+D sign-off + Sid TV replay (B/C/D fixture-complete) |
| TV bar-replay (Sid) | Open |

**Do not** run `ledger_builder` on production TV chart export until hold is explicitly lifted after joint B/C/D sign-off.

---

## Caveat

Same as gate_open / Part C: Python mirror and fixture CSV are **not** TradingView Pine. Fixture tests prove ingestion logic; TV replay confirms export encoding on chart.
