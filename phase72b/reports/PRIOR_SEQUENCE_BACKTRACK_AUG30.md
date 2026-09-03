# Phase72B — Prior-Sequence Backtrack (Aug 30)

## Verdict: `TV_REFERENCE_INSUFFICIENT_FOR_BACKTRACK`

Session prefix: **2026-08-30 17:00 Chicago**  
Forensic window: **20:20 → 20:36 Chicago**

---

## 1. Python path (exact timestamps)

| Time CHI | Event | State | Details |
|----------|-------|-------|---------|
| 20:17 | ARMED_SHORT begins | ARMED_SHORT | ctx invalidation path |
| 20:20–20:26 | ARMED_SHORT continues | ARMED_SHORT | `raw_short=True`, `decE_S=TAKE` on several bars — **no SIGNAL_SHORT fired** (opp/gating) |
| 20:27 | Context invalidation | ARMED_SHORT → **WATCH** | ctx **BULLISH** vs armed SHORT |
| **20:28** | **SIGNAL_LONG** | WATCH → **IN_LONG** | close **29333.0**, ATR **18.0893**, evL=**5**, evS=2 |
| **20:29** | **ENTER_LONG** | IN_LONG → **LONG_ACTIVE** | entry **29335.25** (open), ATR **17.4821**, stop **29317.77**, target **29378.96** |
| 20:30–20:32 | In trade | LONG_ACTIVE | stop/target held |
| **20:33** | **EXIT_STOP** | LONG_ACTIVE → **COOLDOWN** | close 29318.25, reason **M0_STOP**, `cooldown_rem=3` |
| 20:34 | Cooldown | COOLDOWN | rem=2, evS=**7**, gate closed |
| 20:35 | Cooldown | COOLDOWN | rem=1, evS=**8**, gate closed, **no entry** |
| 20:36 | Cooldown ends | COOLDOWN → WATCH | rem=0 |

No separate `ARMED_LONG` bar — **same-bar WATCH → IN_LONG → SIGNAL** at 20:28 (Pine-consistent single-bar arm+take).

---

## 2. TV path from manual references (20:20–20:36)

| Time CHI | Source | TV event | Confidence |
|----------|--------|----------|------------|
| 20:20–20:33 | — | **TV_REFERENCE_UNKNOWN** | No AUTO labels recorded |
| ~20:34 | FIRST_TV_REFERENCE notes | **SIGNAL_SHORT** (~21:34 NY) | Readable in notes, **no formal OBS row** (no OHLC/state) |
| **20:35** | OBS-AUG30-003 | **ENTER_SHORT** | SHORT_ACTIVE, entry 29312.50, ev=7, close 29310.75 |
| **20:37** | OBS-AUG30-004 | **EXIT_STOP** | COOLDOWN |

**Not documented on screenshot / observations:**
- SIGNAL_LONG @ 20:28
- ENTER_LONG @ 20:29
- EXIT_STOP @ 20:33 (LONG)

---

## 3. Earliest comparable event

Within **documented** TV references in 20:20–20:36, the earliest is **OBS-AUG30-003 @ 20:35 ENTER_SHORT**.

At 20:35 (strict order):

| Layer | TV | Python | Pass |
|-------|-----|--------|------|
| OHLC | 29310.75 | 29310.75 | ✓ |
| ATR | 14.7679 | 14.7679 | ✓ |
| FEATURES | ev=7 | evS=8 | ✗ (see §6) |
| STATE | SHORT_ACTIVE | COOLDOWN | ✗ |
| ENTRY | yes | no | ✗ |

**First differing field (documented compare):** STATE (downstream of Python LONG exit @ 20:33).

**Cannot backtrack to 20:28 root cause:** TV does not establish whether Pine fired SIGNAL_LONG @ 20:28. Outcome **D** — insufficient reference for 20:20–20:33.

---

## 4. Evidence @ 20:35 — SECONDARY

`_evidence()` in `pine_features.py` uses **only** OHLC/HTF context (location, 15m/5m, reactions). It does **not** depend on:

- position state
- cooldown
- armed direction
- trade direction
- opportunity memory

At **20:34** Python `evS=7` — **matches TV ev=7** on the documented enter label (signal likely one bar earlier per notes).

At **20:35** Python `evS=8` — one bar later during cooldown; mismatch is **bar timing + market update**, not FSM-contaminated evidence math.

**Classification:** 20:35 ev=7 vs 8 is **SECONDARY** to path divergence (Python LONG stop → cooldown blocks SHORT entry TV shows).

---

## 5. Python-only finding (hypothesis, not proven against TV)

Python took **SIGNAL_LONG @ 20:27→20:28** immediately after **ARMED_SHORT invalidation** on ctx flip to BULLISH. TV documented path in same window is **SHORT** (~20:34 signal, 20:35 enter).

If TV confirms **no LONG** at 20:28, first divergence is likely **SIGNAL @ 20:28** (outcome C). **Cannot assert without TV reference.**

---

## 6. Screenshot needed

```
Date:     2026-08-30
Window:   20:20 – 20:36 America/Chicago
Symbol:   NQ1! 1-minute
Script:   Phase72A Autonomous Trader
Labels:   AUTO labels ON (teal)
Optional: Phase72B manual parity table
```

Must show readable AUTO labels for any SIGNAL/ENTER/EXIT in 20:20–20:33.

---

## 7. Code changes

**None.** Root cause not proven; no mirror/Pine edits.

---

## 8. Regression note

Previously passed **20:46 / 20:47** parity unchanged; no rerun required until backtrack reference supplied.
