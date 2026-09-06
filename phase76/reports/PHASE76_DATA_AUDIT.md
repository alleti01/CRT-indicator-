# Phase76 — Data Audit

**Checkpoint 00:** `PASS`

## Primary stack

| Field | Value |
|-------|-------|
| Symbol | NQ.v.0 |
| Source | Databento ohlcv-1m (stitched local CSV) |
| Continuous | Databento GLBX.MDP3 volume continuous (NQ.v.0) |
| Start (UTC) | 2017-10-01 17:00:00-05:00 |
| End (UTC) | 2026-09-02 10:48:00-05:00 |
| 1m bars | 3,140,775 |
| Timezone (research) | America/New_York |
| Research level | **LEVEL 1** |

## Availability

| Data type | Available |
|-----------|-----------|
| 1m OHLCV | Yes |
| Trade prints | Yes (pilot Jan 2024 only) |
| Aggressor side | Yes (pilot) |
| TRUE volume-at-price | **No** |
| BBO / quotes | No |
| Depth (MBP/MBO) | No |

## Profile reconstruction

All VAH/VAL/POC/HVN/LVN use **`BAR_APPROX_PROFILE`** — volume uniformly distributed across each bar's high–low range.

This is **not** exact volume-at-price. Never treat as TRUE_PROFILE.

## Loaded files

- `/Users/anishalleti/CRT indicator/phase16/data/raw/nq_continuous_1m_oos_20171001_20201201.csv`
- `/Users/anishalleti/CRT indicator/phase18/data/raw/nq_continuous_1m_raw.csv`
- `/Users/anishalleti/CRT indicator/phase16/data/raw/nq_continuous_1m_20231201_20260626.csv`
- `/Users/anishalleti/CRT indicator/phase16/data/raw/nq_continuous_1m_postwindow_to_20260629T0000CT.csv`
- `/Users/anishalleti/CRT indicator/phase58j/data/nq_continuous_1m_lw_extension.csv`

## Order-flow gate (Phase76-OF)

Blocked until an auction family survives information gates. Full-history trades not available.

