# First Divergence — OBS-AUG30-001 (RESOLVED)

Timestamp: 2026-08-30 20:46:00 America/Chicago

## Root cause

**Prefix / window guard mismatch** — not FSM gating logic, evidence, or thresholds.

`AutonomousMirrorEngine.on_bar()` gated Layer A with:

```python
if i >= warmup and i < len(s.cl) - 61:
```

When `run_mirror()` sliced M1 to a short trace window (`end_i ≈ center+6`), `len(s.cl)` was ~3232 while the target bar local index was ~3226. The guard required `i < 3171`, so **FSM logic did not run** on bars T-10..T+5. State froze at the last processed bar (`SHORT_ACTIVE` from an earlier trade).

With a full session `end_i`, the guard passed and the mirror correctly fired `SIGNAL_SHORT` / `IN_SHORT` at 20:46.

## Pine evaluation order (20:46 bar)

On `barstate.isconfirmed` (Layer A):

1. Coerce `p58State` 1/-1 → 2/-2 if `p58InTrade`
2. Finalize p58 entry on `p58EntryBar`
3. Phase71 pending entry at `pendingSignalBar + 1`
4. Phase71 position management (M0/T5/60m)
5. Phase58 internal trade management
6. Cooldown decrement
7. Signal generation (if gate open): WATCH→ARMED, then ARMED→raw take → `f_decideE` → P4/H1 → `pendingTake` + `lastAction=SIGNAL_*` + `p58InTrade` + **`p58State := 2/-2`**
8. Clear `p58BlockSignals`

Order: **raw/take → decideE → P4/H1 → signal flags → state transition to IN_* (same bar) → entry next bar**.

## Pine vs Python transition (SHORT TAKE)

**PINE** (when `total >= takeThreshold` and `isNew` and `decE == "TAKE"` and not P4/H1 abstain and not pos active):

```
pendingTake := true
lastAction := "SIGNAL_SHORT"
p58InTrade := true
p58State := -2
```

**PYTHON** (same path): `signal_short=True`, `p58_in_trade=True`, `p58_state=-2`

**First differing boolean (before fix):** `i < len(s.cl) - 61` was **False** on short windows → entire signal block skipped.

## Fix

File: `phase72b/python/autonomous_mirror_engine.py`

- Replace `len(s.cl) - 61` guard with explicit `run_end_i` from `run()`.
- Align `_state_label()` with Pine `f_p72bStateLbl()` (`IN_*` uses `p58_trade_dir` when `p58_in_trade`).

## Parity after fix

| Time CHI | Layer | TV | Python | Pass |
|----------|-------|-----|--------|------|
| 20:46 | STATE | IN_SHORT | IN_SHORT | ✓ |
| 20:46 | SIGNAL | SIGNAL_SHORT | signal_short=True | ✓ |
| 20:47 | ENTER | 29310.00 | 29310.00 | ✓ |
| 20:47 | STOP | 29325.25 | 29325.14→29325.25 tick | ✓ |
| 20:47 | TARGET | 29272.25 | 29272.14→29272.25 tick | ✓ |

## Verdict

`FIRST_STATE_DIVERGENCE_FIXED`
