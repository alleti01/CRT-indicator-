# Phase59 Source Map — Frozen D → P4 → H1 → M1

Authoritative implementation for **Phase58J-LW** canonical replay.  
Pipeline entry point: `phase58j/tools/last_week_replay.py`

## Stack overview

```
Phase58 v1 TraderEngine (raw 1M signals)
        ↓
Phase58D variant E (online opportunity memory + evidence TAKE/WAIT/PASS)
        ↓
Phase58F compute_confidence + policy P4
        ↓
Phase58G enrich (HIGH_CONFLICTED subtype flags)
        ↓
Phase58H model H1 (surgical abstain)
        ↓
Canonical entry (signal bar T → entry open T+1)
        ↓
Phase58I M1_1.0 management (1.0 ATR stop, 2.5R, 60m, stop-first)
```

---

## A. Phase58D opportunity creation

| Item | Python |
|------|--------|
| **File** | `phase58/research/trader_engine.py` |
| **Function** | `TraderEngine.on_bar_close`, `_take_trade` |
| **Variables** | `signal_i`, `entry_i=i+1`, `direction`, `armed_i` |
| **Pine equivalent** | `phase59/pine/phase59_canonical_live.pine` — Phase58 state machine (ARMED→TAKE) |

Raw Phase58 TAKE signals feed Phase58D; they are **not** final canonical entries.

---

## B. Opportunity memory

| Item | Python |
|------|--------|
| **File** | `phase58d/research/opportunity_memory.py` |
| **Class** | `OpportunityMemory.match_or_create` |
| **Variables** | `structural_gap_bars=30`, `expire_bars=45`, `_cur_opp_id`, `is_new` |
| **Pine equivalent** | Pine `var` stream state: `activeOppId`, `activeDir`, `activeStartBar`, `structGap` |

Same-opportunity suppression: new ID when direction flips or `i - last_signal_i > structural_gap`.

---

## C. TAKE / WAIT / PASS

| Item | Python |
|------|--------|
| **File** | `phase58d/research/evidence.py` |
| **Functions** | `compute_evidence`, `decide` |
| **Variant E rule** | `total >= take_threshold(4)` → TAKE; reaction≥1 and total≥3 → WAIT; else PASS |
| **Pine equivalent** | Evidence sum from location + direction + reaction + contradiction; `decide` thresholds in Pine |

---

## D. P4 (Phase58F)

| Item | Python |
|------|--------|
| **File** | `phase58f/research/policies.py` |
| **Function** | `apply_policy(df, "P4")` |
| **Logic** | ABSTAIN if strong HTF contra (LONG+BEARISH 15m+DOWN/STRONG_DOWN, or SHORT mirror) **and** `reversal_support in (NONE, WEAK)` |
| **Pine equivalent** | `p4Abstain()` in `phase59_canonical_live.pine` |

---

## E. HIGH_CONFLICTED

| Item | Python |
|------|--------|
| **File** | `phase58g/research/forensics.py` |
| **Function** | `classify_high_subtype` |
| **Logic** | HIGH band + `missing_vh_confirm` → `HIGH_CONFLICTED` |
| **Pine equivalent** | `highConflicted` flag from confidence reason codes |

---

## F. HTF contradiction (H1)

| Item | Python |
|------|--------|
| **File** | `phase58h/research/filters.py` |
| **Function** | `h1_mask`, `apply_h_model(..., "H1")` |
| **Logic** | ABSTAIN when `(high_subtype == HIGH_CONFLICTED) & htf_contra_code` (P4 abstain also via union) |
| **Pine equivalent** | `h1Abstain = highConflicted and htfContraCode` |

---

## G. H1 model

| Item | Python |
|------|--------|
| **File** | `phase58h/research/filters.py` |
| **Function** | `apply_h_model` |
| **Pine equivalent** | Combined P4 + H1 gate before pending entry |

---

## H. ATR

| Item | Python |
|------|--------|
| **Files** | `phase45/execution/data_1m.py`, `phase58j/research/lw_data.py` |
| **Definition** | `(high - low).rolling(14).mean()` on 1M |
| **Usage at M1** | `phase58b/research/simulation.py` `_atr()` — fallback scan 5 bars |
| **Management** | `phase58i/research/management.py` `_simulate_one` uses ATR at `entry_i` |
| **Pine equivalent** | `ta.sma(high - low, 14)` — **not** `ta.atr()` (RMA/TR) |

---

## I. Canonical entry convention

| Item | Python |
|------|--------|
| **File** | `phase58d/research/engine.py` |
| **Function** | `run_variant` lines 76–77 |
| **Rule** | Decision on closed bar `signal_i`; `entry_i = signal_i + 1`; `entry_price = m1_op[entry_i]` |
| **Pine equivalent** | Pending entry queue; TAKE label on signal bar; ENTRY label on `bar_index+1` |

---

## J. M1 stop / target / time

| Item | Python |
|------|--------|
| **File** | `phase58i/research/management.py` |
| **Function** | `_walk_managed`, `simulate_management(..., "M1_1.0")` |
| **Stop** | `1.0 * ATR(entry_i)` |
| **Target** | `2.5R` |
| **Max hold** | 60 bars after entry; **entry bar excluded** (`i = ei; while i < n-1: i += 1`) |
| **Collision** | Stop checked **before** target (LONG: low≤stop first) |
| **Pine equivalent** | `manageActiveTrades()` loop, `stopFirst` ordering |

---

## K. 5M context

| Item | Python |
|------|--------|
| **File** | `phase58b/research/context_5m.py`, `phase58d/research/context_maps.py` |
| **Function** | `ctx5_at_1m(m, i, cfg)` → `compute_5m_structure(m, j, cfg)` |
| **Alignment** | `j = m.m1_to_m5[i]` — last closed 5M bar |
| **Pine equivalent** | `request.security(..., "5", ..., lookahead=barmerge.lookahead_off)` |

---

## L. 15M context

| Item | Python |
|------|--------|
| **File** | `phase58b/research/context_15m.py`, `phase58d/research/context_maps.py` |
| **Function** | `ctx15_at_1m` |
| **Alignment** | Via 5M bridge: `phase53/research/data.py` `align_htf_to_1m`, `htf_bar_index` |
| **Pine equivalent** | `request.security(..., "15", ..., lookahead=barmerge.lookahead_off)` |

---

## M. Confidence / features

| Component | File | Function |
|-----------|------|----------|
| Active move | `phase58e/research/active_move.py` | `active_move_at_bar` |
| Structure | `phase58e/research/structure.py` | `structural_features`, `structure_context` |
| Confidence | `phase58f/research/confidence.py` | `compute_confidence` |
| Forensics flags | `phase58g/research/forensics.py` | `enrich` |

---

## Authoritative last-week replay

| Item | Value |
|------|-------|
| **Script** | `phase58j/tools/last_week_replay.py` |
| **Data** | `phase58j/research/lw_data.py` → `build_mtf_arrays_lw()` |
| **Canonical CSV** | `phase58j/results/last_week_all_canonical_trades.csv` |
| **Expected** | 126 entries (62 LONG, 64 SHORT); M1: 55 TARGET, 71 STOP, 0 TIME |

---

## Phase59 artifacts

| Artifact | Role |
|----------|------|
| `phase59/tools/phase59_parity.py` | Reference export + parity harness |
| `phase59/research/pine_equivalent_engine.py` | Bar-orchestrated frozen stack |
| `phase59/reference/phase59_python_reference.csv` | Bar-level parity dataset |
| `phase59/pine/phase59_canonical_live.pine` | TradingView indicator (automatic signals) |

---

## Frozen config hashes (must not drift)

| Config | Hash |
|--------|------|
| phase58_v1 | `facad8ebfae648be` |
| phase58d | `3c25fbacad3fff92` |
| phase58f | `956f66036a568820` |
| phase58h | `4db76ffe5f9b701d` |
| phase58i | `c104ebd37590db03` |
