# Phase72A Causality / Repaint Audit (Phase 1)

**Status:** Phase 1 complete — **ready for review before Phase 2**  
**Verdict:** **NO CONFIRMED_REPAINT** on Layer A live gates  
**Frozen Pine SHA256:** `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f` (verified)  
**Scope:** Read-only audit of `TV_REVIEW/phase72a_autonomous_trader.pine` — **no production edits**

---

## Executive summary

Layer A (the live signal path) evaluates and commits all TAKE / ENTER decisions only inside `if barstate.isconfirmed` (L986+). No mechanism was found that **backdates** a decision, marker, or plotted Layer A value onto a bar earlier than when it was causally knowable.

All `request.security()` calls use explicit `lookahead=barmerge.lookahead_off`. No `ta.barssince`, no negative series offsets (`[-n]`), and no `lookahead_on` anywhere in the file.

Pivot detection uses `rightbars=swingPeriod` (5), which introduces **confirmation lag** (swing extreme at bar T−5 is confirmed at bar T), but state variables (`lastSH`, `m5LastSH`, etc.) update only at confirmation time and feed gates on the **current** bar. That is causal delay, not historical repaint.

**18:49 marker vs 18:59 alert:** Resolved as **alert/configuration event mismatch**, not Pine backdating. See §6.

**Phase 2 gate:** No CONFIRMED_REPAINT on live gates → Phase 2 may proceed **after operator review** of this report.

---

## Methodology

1. Full-text scan of frozen Pine + automated catalog (`phase72a_causality/diagnostics/scan_pine_causality.py` → `PINE_CAUSALITY_SCAN.json`).
2. Manual trace of each hit to Layer A gate / marker / plot consumers.
3. Replay verification:
   - Historical marker parity: `phase72a_latency/diagnostics/replay_entry_events.py` (200/200 PASS).
   - Prefix invariance + signal→entry timing: `phase72a_causality/diagnostics/replay_gate_causality.py` (26 signals across 2 windows, 0 violations).
4. Cross-check with prior latency audit (`phase72a_latency/reports/PHASE72A_LATENCY_FINAL_REPORT.md`).

**Replay proxy note:** TradingView bar-by-bar replay was not run inside this environment. Prefix invariance (full history vs truncated prefix → identical tail events) is the standard causality test already used in Phase72B parity work and is equivalent to stepping forward bar-by-bar without future data. Manual TV bar replay on the Aug 30 forensic window remains recommended for operator sign-off but is not blocking given consistent automated results.

---

## Search-target inventory

| Search target | Found | Layer A impact |
|---------------|-------|----------------|
| `ta.pivothigh` / `ta.pivotlow` | 4 (2×1M, 2×5M via security) | Context, location, 5M structure scores |
| `rightbars` (= `swingPeriod`, 5) | All pivots symmetric 5/5 | Confirmation lag only |
| Negative / forward offsets `[-n]` | **0** | — |
| `ta.valuewhen` | 4 (shCur/shPrev/slCur/slPrev) | 1M swing context |
| `ta.barssince` | **0** | — |
| `request.security` | 9 | All HTF completed-bar feeds |
| Missing / non-explicit lookahead | **0** | All 9 calls: `lookahead_off` |
| Cached `bar_index` compared cross-bar | `curOppLastSi`, `pendingSignalBar`, `p58EntryBar` | All compared at **current** bar only; writes are forward schedules (`+1`) or same-bar |
| “Wait N bars / confirmation” patterns | Pivot rightbars; T+1 entry | Causal by design |

---

## Candidate table (constructs → gates → classification)

### A. HTF / security

| ID | Location | Feeds | Knowable | Status | known_at (gate eval) |
|----|----------|-------|----------|--------|----------------------|
| SEC-01 | L178-179 `m5C_comp…` `[1]` + `lookahead_off` | Developing alias fallbacks, debug | Prior **completed** 5M bar | **SAFE** | 0 |
| SEC-02 | L180-181 `m15C_comp…` | `f_ctx15`, evidence contra | Prior completed 15M bar | **SAFE** | 0 |
| SEC-03 | L182-183 `m5BarTime` / `m15BarTime` | Forensic tables only (Layer B) | Completed HTF time | **SAFE** | N/A (display) |
| SEC-04 | L191-192 `m5PivotH/L` pivots on 5M | `f_ctx5`, `f_loc5m`, 5M HH/HL | Pivot confirmed on completed 5M bar stream | **SAFE** | 0 |
| SEC-05 | L205-207 `m15H4`, `m15L4`, `m15C12` | `f_ctx15` | HTF lookback [4]/[12] on **completed** bars | **SAFE** | 0 |

### B. 1M pivots & swings

| ID | Location | Feeds | Knowable | Status | known_at (gate eval) |
|----|----------|-------|----------|--------|----------------------|
| PIV-01 | L218-219 `pivotHigh/Low(high/low, 5, 5)` | `lastSH/SL`, `shAtI*`, `slAtI*` | Non-`na` only after 5 right bars → updates `lastSH` at confirmation bar | **SAFE** | 0 |
| PIV-02 | L232-235 `ta.valuewhen` ×4 | `shAtI`, `shAtI10`, `slAtI`, `slAtI10` | Forward-filled from past pivot confirmations | **SAFE** | 0 |
| PIV-03 | L237-240 `shAtI10` fallback `lastSH[10]` | `f_computeContext`, `f_structFeatures` | Backward series index only | **SAFE** | 0 |
| PIV-04 | L193-202 `m5LastSH/SL` vars | `f_ctx5`, `f_loc5m` | Updated when `m5PivotH/L` non-na on 1M | **SAFE** | 0 |

**Pivot semantics (not repaint):** At bar T when `not na(pivotHigh)`, the returned price is the high at bar T−5. Gates at bar T use the **post-confirmation** stored level. The chart does not backdate TAKE markers to T−5.

### C. Developing HTF buckets

| ID | Location | Feeds | Status | known_at |
|----|----------|-------|--------|----------|
| DEV-01 | L116-140 developing 5M bucket | `m5H/L/C/O`, progress, ATR | **SAFE** — incremental OHLC on current 1M bar | 0 |
| DEV-02 | L142-162 developing 15M bucket | `m15H/L/C/O`, `f_ctx15`, progress | **SAFE** | 0 |

### D. Lookback helpers (backward-only)

| ID | Location | Feeds | Status | known_at |
|----|----------|-------|--------|----------|
| LB-01 | L247-259 `ta.highest/lowest`, `ta.sma` | Location, progress, impulse | **SAFE** — `[n]` is past-only | 0 |
| LB-02 | L518-606 reaction helpers (`close[1]`…`close[4]`) | `reactScLong/Short` → evidence | **SAFE** | 0 |
| LB-03 | L678-687 `f_activeMove` `close[progressLb*]` | Confidence / P4 / H1 inputs | **SAFE** | 0 |

### E. Layer A timing & stored bar indices

| ID | Location | Feeds | Status | known_at |
|----|----------|-------|--------|----------|
| TIM-01 | L986 `barstate.isconfirmed` guard | All Layer A decisions | **SAFE** — bar-close commit | 0 |
| TIM-02 | L1238 `pendingSignalBar := bar_index` | TAKE → ENTER chain | **SAFE** | 0 |
| TIM-03 | L1004 `bar_index == pendingSignalBar + 1` | ENTER at T+1 open | **SAFE** — forward schedule | 0 |
| TIM-04 | L1251 `p58EntryBar := bar_index + 1` | Internal Phase58 trade | **SAFE** — forward schedule | 0 |
| TIM-05 | L1186 `(bar_index - curOppLastSi) > structGap` | Phase58D opportunity memory | **SAFE** — compares stored index to current | 0 |
| TIM-06 | L1539-1542 `signalBar := bar_index - 1` | **DEBUG only** (`DEBUG_MANUAL_SIGNAL=false`) | **SAFE** — not live path | N/A |

### F. Markers & plots (Layer A vs Layer B)

| ID | Location | Live? | Status | Notes |
|----|----------|-------|--------|-------|
| MK-01 | L1244-1245 SIGNAL label `@ bar_index` | Yes (`showTake`) | **SAFE** | TAKE at signal bar T |
| MK-02 | L1018-1020 ENTER label `@ bar_index` | Yes (`showEntry`) | **SAFE** | Only when `bar_index == pendingSignalBar + 1` |
| MK-03 | L1276-1285 parity reference labels | No (`debugParityMarkers=false`) | **SAFE** | Layer B |
| MK-04 | L1589-1602 P72B export plots | No (`exportParity=false`) | **SAFE** | Gated + `barstate.isconfirmed` |
| MK-05 | L1604-1607 `alertcondition` | No (exportParity off) | **SAFE** | Not production webhook path |

---

## Ledger gate `known_at_bar_offset` (Phase 2 input)

All named ledger gates evaluate at **signal bar close** with offset **0**. Sub-features (pivots, HTF completion) embed historical lag inside the value available at that close, but no gate boolean requires shifting forward information onto an earlier bar.

See machine-readable: `GATE_KNOWN_AT_OFFSETS.csv`

| Gate | Offset | Rationale |
|------|--------|-----------|
| `armed_long` / `armed_short` | 0 | ARMED transition on confirmed bar |
| `evidence_threshold_*` | 0 | Score computed on confirmed bar |
| `decide_e_*` | 0 | `f_decideE` on same-bar evidence |
| `p4_keep_*` / `h1_keep_*` | 0 | Same-bar confidence outputs |
| `gate_open` | 0 | Same-bar FSM + position checks |
| `not_in_cooldown` | 0 | Same-bar `p58State` |
| `take_long` / `take_short` | 0 | `pendingTake` set on TAKE bar close |

**Entry fill convention (separate from gate_state):** executable entry is **T+1 open** (`ENTRY_OFFSET_BARS=1` in signal_ledger). ENTER markers/alerts must not be attributed to bar T.

---

## Replay verification results

### 1. Historical marker parity (frozen Phase69 entries)

```
PHASE72A_FREEZE_OK = TRUE
Historical parity: 200 PASS / 0 FAIL
Signal→Entry delta = 1 bar: 200/200
```

Artifact: `phase72a_latency/reports/HISTORICAL_MARKER_PARITY.csv`

### 2. Prefix invariance + signal→entry timing

| Window | Signals | Prefix pass | Enter on T+1 only |
|--------|---------|-------------|-------------------|
| Aug 28 session (08:30–16:00 CHI) | 15 | ✓ (0 mismatches / 200 tail bars) | 15/15 |
| Aug 30 evening (17:00–22:30 CHI) | 11 | ✓ (0 mismatches / 200 tail bars) | 11/11 |

Artifact: `phase72a_causality/reports/REPLAY_GATE_CAUSALITY.json`

No case found where `enter_*` fired on the same bar as `signal_*`. No prefix mismatch → no future-data leakage detected in the mirror of Layer A semantics.

---

## §6 — 18:49 marker vs 18:59 alert (same replay pass)

**Root cause class:** `PHASE72A_ALERT_CONFIGURATION_ERROR` (not Layer A repaint)

| Event | Causal bar | Marker text | Knowable |
|-------|------------|-------------|----------|
| TAKE / decision | T (e.g. 18:49 close) | `SIGNAL_LONG` / `SIGNAL_SHORT` | End of bar T |
| Executable entry | T+1 open (e.g. 18:50) | `ENTER_LONG` / `ENTER_SHORT` | Start of bar T+1 |

Findings:

1. Layer A **never** places `ENTER_*` labels on bar T (L1004, L1018-1020).
2. A **10-minute** gap cannot be produced by legitimate T+1 scheduling (1 bar ≈ 1 minute on 1M chart).
3. Production webhooks were configured for `SIGNAL_*` events while operators often colloquially call SIGNAL markers “enter” — plus stale/mispaired alerts (`phase72a_latency/reports/PHASE72A_LATENCY_FINAL_REPORT.md`).
4. Frozen production Pine has **no live `alert()`** — only disabled `alertcondition` behind `exportParity=false`.

**Replay conclusion:** Not CONFIRMED_REPAINT. Pairing / alert config issue.

---

## SUSPECT items reviewed — none upgraded to CONFIRMED_REPAINT

| SUSPECT | Review outcome |
|---------|----------------|
| Pivot rightbars=5 | Confirmation lag; state updates at confirmation bar; prefix test PASS |
| `valuewhen` on pivots | Reads confirmed pivot history only |
| Developing HTF vs completed HTF mix | Intentional Phase60 design; completed paths use `[1]` + `lookahead_off` |
| `m15H4` / `m15C12` HTF offsets | Backward within completed HTF series |
| Phase72B export plots | Layer B, default off; do not affect Layer A |

---

## Explicit out of scope (Phase 1)

- No modifications to frozen Phase72A Pine
- No alert configuration changes
- No gate instrumentation (Phase 2)
- No signal_ledger fixes (Phase 2)

---

## Phase 2 readiness checklist

| Item | Status |
|------|--------|
| CONFIRMED_REPAINT on live gates | **None found** |
| `known_at_bar_offset` per gate documented | **Yes** (`GATE_KNOWN_AT_OFFSETS.csv`) |
| Frozen SHA256 verified | **Yes** |
| Operator review of this report | **Pending** |

**Recommendation:** Proceed to Phase 2 (M0 fixture trace, replace Phase72B gate source, instrumentation) after operator sign-off on this report.

---

## Artifacts

| File | Purpose |
|------|---------|
| `phase72a_causality/reports/PHASE72A_CAUSALITY_AUDIT.md` | This report |
| `phase72a_causality/reports/PINE_CAUSALITY_SCAN.json` | Automated search catalog |
| `phase72a_causality/reports/REPLAY_GATE_CAUSALITY.json` | Prefix + signal timing replay |
| `phase72a_causality/reports/GATE_KNOWN_AT_OFFSETS.csv` | Phase 2 offset input |
| `phase72a_causality/diagnostics/scan_pine_causality.py` | Re-runnable Pine scan |
| `phase72a_causality/diagnostics/replay_gate_causality.py` | Re-runnable replay proxy |

**Re-run:**

```bash
python3 phase72a_causality/diagnostics/scan_pine_causality.py
python3 phase72a_causality/diagnostics/replay_gate_causality.py
python3 phase72a_latency/diagnostics/replay_entry_events.py
```
