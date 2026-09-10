# Phase81 — SHORT-Only Logic Improvement

- **RESEARCH_ENTRY_STREAM:** PHASE60
- **PHASE72A_HISTORICAL_PARITY_NOT_ESTABLISHED**
- Pine SHA256: `d75ff747a491c176eda588efc945822b8bd4a6aeaaeaf1d2bdea2b7a8e32cc1f`
- Stream hash: `0da41f282174679f`
- M0: {'stop_r': 1.0, 'target_r': 2.5, 'max_hold_minutes': 60, 'collision': 'STOP_FIRST'}
- LONG_STREAM_HASH_BEFORE: `cb8302a18e0957a8`

- **LONG_STREAM_HASH_AFTER:** `cb8302a18e0957a8`
## Baseline
- SHORT N=16664 AvgR=-0.00046 PF=0.999 TotalR=-7.6
- LONG  N=19510 AvgR=0.03004 PF=1.043 (reference only, frozen)
- PORT  N=36174 AvgR=0.01599

## Short Failure Forensics (dominant category by N)
- **LATE_EXTENSION** — N=10117 (60.7% of shorts)

Top loss categories:
- LATE_EXTENSION: N=10117 AvgR=-0.995 TotalR=-10065
- GOOD_SHORT: N=4741 AvgR=2.500 TotalR=11852
- CHOP_SHORT: N=1022 AvgR=-1.000 TotalR=-1022
- NO_BEARISH_COMMITMENT: N=480 AvgR=-0.992 TotalR=-476
- FAILED_BOUNCE_MISSED: N=147 AvgR=-1.000 TotalR=-147

## Directional Control
- REAL short AvgR: -0.00046
- RANDOM direction AvgR: 0.00451
- Baseline shorts do not beat random at entry timestamps

## Model Search
- Hypotheses tested: 15
- Validation survivors: 0

## Top models by Δ short AvgR
- S8: N=2629 retention=15.8% ΔAvgR=+0.1006 val_AvgR=0.0529 val_pass=False
- S4: N=249 retention=1.5% ΔAvgR=+0.0406 val_AvgR=-0.0900 val_pass=False
- S5: N=3242 retention=19.5% ΔAvgR=+0.0271 val_AvgR=-0.0816 val_pass=False
- S3: N=3206 retention=19.2% ΔAvgR=+0.0005 val_AvgR=0.0097 val_pass=False
- S0: N=16664 retention=100.0% ΔAvgR=+0.0000 val_AvgR=-0.0153 val_pass=False

**Verdict:** `PHASE81_NO_SHORT_EDGE`

Elapsed: 3.7s
