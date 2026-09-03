# Phase 50 — Python Logic Manifest

Frozen model: **Phase44 (15M) → B1 Micro-BOS (1M, 10 min) → M0**

Python is the source of truth. Pine must translate these implementations.

## Phase44 — Context / Signal

| Component | Python file | Function / logic | Key parameters |
|-----------|-------------|----------------|----------------|
| Signal generation | `phase37/concurrent.py` | `replay_concurrent()` | RTH 0930-1600, displacement, BOS retest, reversal pool |
| Impulse gate | `phase40/filter.py` | `impulse_3bar >= IMPULSE_THRESHOLD` | `0.65` |
| Quality score | `phase44/simple_score.py`, `phase45/frozen.py` | `evaluate_quality()` | `Q_RAW_LO/HI`, `Q_PASS_MIN=36.493...` |
| Confidence tier | `phase45/frozen.py` | `confidence_tier()` | A+ ≥ 63.198, A ≥ 46.077, B ≥ 36.493 |
| Accepted signals CSV | `phase44/results/.../quality_reference_all_signals.csv` | `accepted=True` | N=2275 |
| Pine Phase44 port | `phase44/results/.../NQ15_PHASE44_QUALITY_INDICATOR.pine` | Full state machine | Embedded in `phase44ExportBundle()` |

**Pine equivalent:** `request.security(..., "15", phase44ExportBundle(), lookahead=barmerge.lookahead_off)`

**Timing:**
- `marker_bar_timestamp` = 15M bar open when signal fires
- `actionable_timestamp` = marker + 15 minutes (15M bar close)
- Phase44 available to 1M layer at actionable time

## B1 Micro-BOS

| Component | Python file | Function | Parameters |
|-----------|-------------|----------|------------|
| B1 confirmation | `phase45/execution/confirm.py` | `confirm_b1()` | window inclusive [start, start+10min] |
| Swing structure | `confirm.py` | `_causal_swing_levels()` | 3-bar pivot: `high[j-1] > high[j-2] and high[j-1] > high[j]` |
| Long trigger | `confirm.py` | `close[i] > swing_high` | close-based break |
| Short trigger | `confirm.py` | `close[i] < swing_low` | close-based break |
| Entry price | `confirm.py` | `close[i]` of confirming bar | — |
| Entry time | `confirm.py` | timestamp of confirming bar | — |
| Window | `phase49/config.py` | `FROZEN_B1_WINDOW_MIN = 10` | inclusive endpoints |

**Pine equivalent:** `causalSwingHigh()`, `causalSwingLow()`, B1 scan on 1M when `time >= actionableMs and time <= windowEndMs`

## M0 Trade Management

| Component | Python file | Function | Parameters |
|-----------|-------------|----------|------------|
| Simulation | `phase45/execution/simulate.py` | `simulate_1m()` | stop-first intrabar |
| Max hold L/S | `config.py` | `MAX_HOLD_CONT = 60` | 1M bars |
| Max hold RL/RS | `config.py` | `MAX_HOLD_REV = 45` | 1M bars |
| Target R | `simulate.py` | fixed 3.0 (L/S), 2.5 (RL/RS) | not price-derived on TARGET exit |
| Entry bar | `simulate.py` | manage from `entry_i + 1` | no exit on entry bar |

**Pine equivalent:** `P50_MAX_HOLD_CONT/REV`, stop checked before target, `p50PosHeld` increment after checks

## Session / Timezone

| Item | Python | Pine |
|------|--------|------|
| Timezone | `America/Chicago` | Chart exchange TZ; use `syminfo.timezone` |
| RTH | `0930-1600` | `inRth(FZ_RTH)` in Phase44 bundle |
| Data source | Databento NQ continuous UTC → Chicago | TV: `CME_MINI:NQ1!` documented in config |

## Overlap / State (Python reference)

- One active B1 wait state on 1M; new Phase44 setup replaces wait if not in trade (`forward_engine.py` pattern)
- Phase44 15M concurrent reversal pool: full port in `phase44ExportBundle()`

## Parity reference export

| Artifact | Generator |
|----------|-----------|
| `python_reference_signals.csv` | `phase50/export_reference.py` — B1_w10 filled + `simulate_1m` |
| Sample | `sample_parity_reference.csv` — 10+ per segment |

**Note:** Canonical stitched OOS uses per-fold B1 window (N=1135). Pine/reference export uses fixed **B1@10min** (N≈1212) for apples-to-apples Pine validation.
