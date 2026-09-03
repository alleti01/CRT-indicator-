# Aug 30 TV Time Correction — Parity Report

## Verdict: `FIRST_DIVERGENCE_AFTER_TIME_CORRECTION`

**Correction:** NY times were previously misread as Chicago (−1h error). AUTO labels print both zones; ground truth is label text.

| TV label | Chicago (correct) | Old wrong CHI |
|----------|-------------------|---------------|
| NY 22:34 | **21:34** | 20:34 |
| NY 22:35 | **21:35** | 20:35 |
| NY 22:45 | **21:45** | 20:37 (wrong bar) |

Prior conclusions at **20:35 / 20:37 / 20:46 / 20:47** → **`INVALIDATED_BY_TV_TIME_CORRECTION`**

---

## Python mirror path (21:25–21:50 CHI)

| Time CHI | Python event |
|----------|--------------|
| **21:29** | **SIGNAL_SHORT** → IN_SHORT, close 29331.50, ATR 13.73, evS=**4** |
| **21:30** | **ENTER_SHORT** @ **29327.00**, stop 29340.625 (→29340.75 tick), tgt 29292.9375 |
| **21:35** | **EXIT_TARGET** (M0_TARGET) → COOLDOWN |
| 21:37 | COOLDOWN → WATCH |
| 21:45 | ARMED_SHORT → WATCH (no exit) |

TV corrected sequence is **5 minutes later** than Python for signal/enter, and exit type/time differ.

---

## Strict parity (corrected TV times)

### 21:34 — SIGNAL_SHORT (OBS-AUG30-005)

| Layer | TV | Python | Pass |
|-------|-----|--------|------|
| OHLC | 29299.00 | 29299.00 | ✓ |
| ATR | 12.2 | 12.2857 | ✓ |
| **FEATURES** | **ev=5** | **evS=6** | **✗** |
| STATE | IN_SHORT | SHORT_ACTIVE | ✗ |
| SIGNAL | yes | no | ✗ |

**First divergence:** FEATURES (ev 5 vs 6)  
*(Python already in trade from 21:30; TV signal bar semantics differ.)*

### 21:35 — ENTER_SHORT (OBS-AUG30-006)

| Layer | TV | Python | Pass |
|-------|-----|--------|------|
| OHLC | 29292.50 | 29292.50 | ✓ |
| ATR | 12.5357 | 12.5357 | ✓ |
| STATE | SHORT_ACTIVE | COOLDOWN | ✗ |
| ENTRY | 29299.00 | no (exited target) | ✗ |
| stop (tick) | 29311.50 | — | ✗ |

**First divergence:** STATE

### 21:45 — EXIT_STOP (OBS-AUG30-007)

| Layer | TV | Python | Pass |
|-------|-----|--------|------|
| OHLC | ~29312.00 | 29312.00 | ✓ |
| ATR | 10.0357 | 10.0357 | ✓ |
| **EXIT** | **EXIT_STOP** | **none** | **✗** |
| STATE | WATCH | WATCH | ✓ |

**First divergence:** EXIT (TV stop exit vs Python no exit on this bar)

---

## Chronological first failure (corrected sequence)

**21:34 SIGNAL_SHORT** — first differing field in strict order: **FEATURES** (ev 5 vs 6), with downstream STATE/SIGNAL mismatch because Python entered at **21:30** not 21:35.

---

## Invalidated prior work

- DIV-003 (20:35 ENTER) — INVALIDATED_BY_TV_TIME_CORRECTION
- DIV-004 (20:20 backtrack) — INVALIDATED_BY_TV_TIME_CORRECTION
- AUG30_MULTI_EVENT_PARITY first failure at 20:35 — INVALIDATED
- PRIOR_SEQUENCE_BACKTRACK insufficient-window conclusion — superseded by corrected labels

No Pine or trading-logic changes.
