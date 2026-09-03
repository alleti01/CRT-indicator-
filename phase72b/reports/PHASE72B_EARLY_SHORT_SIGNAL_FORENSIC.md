# Phase72B — Early SHORT Signal Forensic (Aug 30, corrected CHI timestamps)

**Session prefix:** 2026-08-30 17:00 America/Chicago  
**Forensic window:** 21:24 → 21:35 CHI  
**Valid divergence under investigation:** Python SIGNAL/ENTER 5 bars before TV (21:29/21:30 vs 21:34/21:35)

---

## Executive summary

| Field | Value |
|-------|-------|
| **FIRST differing variable (at 21:29 compare layer)** | `isNewOpp` (opportunity memory) |
| **Pine value (expected, not yet captured on chart)** | `isNewOpp = false` — same-direction SHORT episode `OPP_3226_SHORT` still active |
| **Python value (proven)** | `isNewOpp = true` — prior opp was `OPP_3253_LONG` (direction flip) |
| **Root cause (causal chain)** | At **21:13 CHI**, Python entered `ARMED_LONG`, hit raw take `total≥4` with `decE=PASS`, and **allocated a new LONG opportunity** (`OPP_3253_LONG`) without firing a signal. That cross-direction opp swap made the **21:29 SHORT raw take** qualify as a **new opportunity**, bypassing same-direction dedup that blocked 21:03–21:09. |
| **Upstream trigger (21:13)** | `ctxDir=BULLISH` (bull=4, bear=1) → WATCH→ARMED_LONG + opp id swap |
| **Classification** | Opportunity-memory path divergence; likely upstream ctxDir/FSM at 21:10–21:13 — **Pine reference required before mirror fix** |
| **Files changed** | `phase72b/tools/early_short_signal_forensic.py`, `TV_REVIEW/phase72a_autonomous_trader.pine` (Layer B inspect only) |
| **Trading logic changed** | **NO** |

**Final verdict:** `FIRST_CAUSAL_DIFFERENCE_IDENTIFIED` + `PINE_REFERENCE_REQUIRED_AT_21_29`

---

## 1. Forensic window (Python mirror)

Full bar export: `phase72b/reports/EARLY_SHORT_SIGNAL_FORENSIC.json`  
Generator: `python3 phase72b/tools/early_short_signal_forensic.py`

### Window timeline (Python)

| CHI | State | rawS | totS | evS | isNew | Opp (before→after) | Notes |
|-----|-------|------|------|-----|-------|---------------------|-------|
| 21:24 | WATCH | F | 4 | 7 | Y | OPP_3253_LONG | ctx NEUTRAL, not ARMED |
| 21:25 | WATCH | F | 3 | 6 | Y | OPP_3253_LONG | |
| 21:26 | WATCH→**ARMED_SHORT** | F | 3 | 5 | Y | OPP_3253_LONG | ctx BEARISH arm |
| 21:27 | ARMED_SHORT | F | 3 | 4 | Y | OPP_3253_LONG | below threshold |
| 21:28 | ARMED_SHORT | F | 3 | 3 | Y | OPP_3253_LONG | below threshold |
| 21:29 | ARMED→**IN_SHORT** | **T** | **4** | **4** | **Y** | **OPP_3253_LONG→OPP_3269_SHORT** | **SIGNAL_SHORT** |
| 21:30 | IN_SHORT→SHORT_ACTIVE | F | 5 | 6 | N | OPP_3269_SHORT | ENTER @ 29327 |
| 21:34 | SHORT_ACTIVE | F | 4 | 6 | N | OPP_3269_SHORT | TV signal bar (Python already in trade) |
| 21:35 | SHORT_ACTIVE→COOLDOWN | F | 4 | 6 | N | OPP_3269_SHORT | Python M0_TARGET |

### HTF at 21:29 (causal buckets)

| Field | Python @ 21:29 |
|-------|----------------|
| m5_completed_j | 627639 (new 5m bucket vs 21:28) |
| m15_completed_j | 209136 (new 15m bucket vs 21:28) |
| m5_c / m15_c | 29331.50 / 29331.50 |
| ctx15_state | TRANSITION |

OHLC and ATR at 21:29 already confirmed aligned with TV in prior parity pass.

---

## 2. Python 21:29 — complete SIGNAL_SHORT boolean chain

All values are **pre-signal** (start-of-bar snapshot before FSM mutation):

```
gateOpen                    = TRUE
stateEligible (ARMED_SHORT) = TRUE   (p58_state == -1)
rawShort                    = TRUE   (totS=4 >= takeThreshold=4)
total                       = 4      (ctxSc=2 + locSc=2 + reactSc=1 + contra=-1)
takeThreshold               = 4
isNewOpp                    = TRUE
  curOppDir_before          = "LONG"   (OPP_3253_LONG from 21:13)
  curOppLastSi_before       = 3257
  structGap                 = 30
  bars_since                = 12 (< 30, but direction flip overrides)
decE                        = "TAKE"   (evS=4)
p4Abstain                   = FALSE
h1Abstain                   = FALSE
positionActive              = FALSE
p58InTrade_before           = FALSE
p58BlockSignals_before      = FALSE

→ SIGNAL_SHORT = TRUE
→ p58InTrade := TRUE, p58State := -2 (IN_SHORT)
```

**Why 21:03–21:09 did NOT signal (same session, prior ARMED_SHORT episode):**

| CHI | rawS | isNew | curOppDir | Result |
|-----|------|-------|-----------|--------|
| 21:03–21:09 | TRUE | **FALSE** | SHORT (OPP_3226_SHORT) | curOppLastSi updated only — dedup blocks signal |

---

## 3. Pine reference at 21:29 — inspect configuration

Layer B `inspectTimestamp` default updated to **2026-08-30 21:29 Chicago** (`1788143340000`).

**To capture Pine ground truth:**

1. Paste updated `phase72a_autonomous_trader.pine` into TradingView
2. Enable `manualParityMode = true`
3. Enable `enableInspectBar = true`
4. Navigate chart to **Aug 30 2026 21:29 CHI** (1m NQ continuous)
5. Read orange **P72B INSPECT** label (now includes `opp`, `oppLastSi`, `isNew`)

**Minimum fields to record:**

- st before/after, ctxDir, evL/evS, raw/take/sig, D/P4/H1, gate, opp dir, isNew, lastAction

**Expected Pine @ 21:29 if root cause confirmed:**

- `ARMED_SHORT`, `rawShort=1`, `sigShort=0`, `isNew=N`, `curOppDir=SHORT`

Also inspect **21:13 CHI** (set inspectTimestamp to `1788142980000`) for whether Pine entered `ARMED_LONG` and swapped opp to `OPP_*_LONG`.

---

## 4. First-difference order @ 21:29

| Layer | Match? | Python | Pine (expected) |
|-------|--------|--------|-----------------|
| OHLC | ✓ | 29333.75/29336.25/29327.00/29331.50 | aligned |
| ATR | ✓ | 13.7321 | aligned |
| HTF buckets | ✓ (causal) | m5j=627639, m15j=209136 | verify via inspect |
| Structure/features | ✓ | totS=4, evS=4, ctx=NEUTRAL | likely same if OHLC same |
| **Opportunity memory** | **✗ FIRST** | **isNewOpp=TRUE**, curOppDir=LONG | **isNewOpp=FALSE**, curOppDir=SHORT |
| State before | (downstream) | ARMED_SHORT | ARMED_SHORT (expected) |
| rawShort | (downstream) | TRUE | TRUE (expected) |
| decE | — | TAKE | TAKE (expected) |
| P4/H1 | — | KEEP/KEEP | KEEP/KEEP (expected) |
| SIGNAL | **✗** | **TRUE** | **FALSE (expected)** |

**Stop layer:** OPPORTUNITY MEMORY (`isNewOpp`)

---

## 5. Opportunity memory audit

### Episode chain (Python, Aug 30 evening)

```
20:59  EXIT stop → WATCH (opp OPP_3226_SHORT retained)
21:00  WATCH → ARMED_SHORT; opp lastSi → 3240 (same SHORT episode)
21:03–21:09  rawShort TRUE × 5 bars; isNew=FALSE → no signal (dedup)
21:10  ctx BULLISH → ARMED_SHORT invalidated → WATCH
21:13  ctx BULLISH → ARMED_LONG; rawLong tot=4, decE=PASS
       → NEW opp OPP_3253_LONG (direction flip from SHORT)
21:15–21:17  ARMED_LONG raw updates (no signal, decE=PASS)
21:18  ctx BEARISH → ARMED_LONG invalidated → WATCH
21:26  WATCH → ARMED_SHORT (opp still OPP_3253_LONG)
21:29  rawShort tot=4, isNew=TRUE (LONG→SHORT flip) → SIGNAL_SHORT
```

**Dedup rule (Pine Layer A = Python mirror):**

```pine
isNew = na(curOppId) or dirStr != curOppDir or (bar_index - curOppLastSi) > structGap
```

Cross-direction opp at 21:13 is **by-design** in frozen engine — but if Pine never arms LONG at 21:13, opp stays SHORT and 21:29 dedup blocks.

---

## 6. HTF semantics @ 21:29

- 5m bucket advances 627638 → **627639** on the 21:29 bar (5m close completes causally on this 1m bar).
- 15m bucket advances 209135 → **209136** on the same bar.
- No evidence of future-completed HTF candle injection in Python series builder at this timestamp.
- Feature values at 21:29 use only completed HTF buckets (`m5_completed_j`, `m15_completed_j` indices).

---

## 7. 21:34 secondary (ev=5 vs ev=6)

**Not a separate root cause.** At 21:34:

- Python is already `SHORT_ACTIVE` from 21:30 enter — signal gate closed.
- TV fires fresh `SIGNAL_SHORT` with ev=5 at px 29299.
- Python evS=6 on same bar reflects continued feature evolution while in-trade.

The ev mismatch is **downstream** of the 21:29 timing divergence. Do not patch 21:34 independently.

---

## 8. Fix status

**No mirror fix applied** — awaiting Pine inspect at 21:29 and 21:13 to confirm:

1. Pine `isNewOpp=N` at 21:29 with `curOppDir=SHORT`, OR
2. Pine `ctxDir` differs at 21:10/21:13 (no ARMED_LONG / no LONG opp swap)

If (1) confirmed → fix Python mirror opp path to match Pine (likely suppress cross-direction opp allocation on decE=PASS, or align 21:13 ctxDir).

If Pine Layer A also arms LONG at 21:13 with same opp swap → report `PINE_LAYER_A_LOGIC_DIVERGENCE` (do not silently change Layer A).

---

## 9. Regression targets (after legitimate fix)

| Event | Target |
|-------|--------|
| 21:34 SIGNAL_SHORT | parity |
| 21:35 ENTER_SHORT @ 29299 | parity |
| 21:45 EXIT_STOP | parity |

---

## 10. Parity status (current)

| Check | Status |
|-------|--------|
| 21:34 SIGNAL parity | **FAIL** (Python already in trade) |
| 21:35 ENTRY parity | **FAIL** (Python exited target; TV enters) |
| 21:45 EXIT parity | **NOT TESTED** (downstream) |

---

## Divergence ledger update

| ID | Status | Notes |
|----|--------|-------|
| DIV-005 | OPEN → **ROOT CAUSE NARROWED** | First diff: `isNewOpp` @ 21:29; upstream 21:13 LONG opp swap |
| DIV-006 | NEW | 21:13 ARMED_LONG + OPP_3253_LONG allocation (Python); Pine TBD |

---

## Commands

```bash
# Full forensic JSON
python3 phase72b/tools/early_short_signal_forensic.py

# Session trace centered 21:29
python3 phase72b/tools/trace_timestamp.py \
  --timestamp "2026-08-30 21:29:00" \
  --timezone America/Chicago --before 30 --after 10
```
