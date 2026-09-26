# CDX V3 data extension report — 2026-09-21

Prior package verdict (preserved): `CDX_RE_INSUFFICIENT_INFORMATION`

This run verdict: **`CDX_RE_DATA_EXTENSION_FAIL`**

## 1. Current trusted source (verified, not assumed)

Loader: `phase58j.research.lw_data.load_market_1m_lw`

Stitch:

1. `phase16/data/raw/nq_continuous_1m_oos_20171001_20201201.csv`
2. `phase18/data/raw/nq_continuous_1m_raw.csv`
3. `phase16/data/raw/nq_continuous_1m_20231201_20260626.csv`
4. `phase16/data/raw/nq_continuous_1m_postwindow_to_20260629T0000CT.csv`
5. `phase58j/data/nq_continuous_1m_lw_extension.csv`

| Field | Value |
|---|---|
| First timestamp (index TZ) | 2017-10-01 17:00:00-05:00 America/Chicago |
| Last timestamp (index TZ) | **2026-09-02 10:48:00-05:00 America/Chicago** |
| First UTC | 2017-10-01 22:00:00+00:00 |
| Last UTC | 2026-09-02 15:48:00+00:00 |
| First ET | 2017-10-01 18:00:00-04:00 |
| Last ET | 2026-09-02 11:48:00-04:00 |
| Row count | 3,140,775 |
| Index timezone | America/Chicago (DST-aware) |
| Raw extension timestamps | UTC (`2026-09-02 15:48:00+00:00`) |
| Symbol / contract | Databento **NQ.v.0** volume continuous (`GLBX.MDP3` `ohlcv-1m`) |
| Duplicate timestamps | 0 |
| Monotonic | yes |
| Median bar gap | 1.0 minute |
| Gaps > 90s | 5,951 (weekends, daily maintenance, thin overnight — not filled) |
| Gaps ≥ 30h | 465 (typical weekend / holiday) |
| Session handling | No RTH filter in the loader. RTH 09:30–16:00 ET ≈ 885,342 bars; other ≈ 2,255,433 |
| OHLC invalid | 0 |

Timestamps are **not** ET in the file. Matching must convert `America/Chicago` or UTC → `America/New_York`.

## 2. Extension attempt

Required next bar: **2026-09-02 15:49:00 UTC** through at least **2026-09-22 03:59:00 UTC** (covers 2026-09-21 23:59 ET).

Compatible method: same as `phase16/download_databento.py` / `phase72b/tools/extend_lw_data.py` — `NQ.v.0`, continuous, ohlcv-1m.

On this machine:

- `databento` package: installed (0.64.0)
- `DATABENTO_API_KEY`: **absent** (env, repo `.env`, `~/.databento`, zshrc)
- Local CSVs after 2026-09-02: **none**
- `nq_continuous_1m_lw_extension_append.csv` already ends 2026-09-02 15:48 UTC (already merged)

`python3 -m cdx_research.python.extend_same_series` exited 2: key missing.

No Yahoo / TV / NQ1! splice was performed.

## 3. Continuity

**No new rows.** Join around Sep 2 was not created.

Last 3 trusted raw rows (UTC):

| timestamp UTC | open | high | low | close | volume | symbol |
|---|---|---|---|---|---|---|
| 2026-09-02 15:46:00Z | 29157.75 | 29167.50 | 29156.00 | 29166.50 | 694 | NQ.v.0 |
| 2026-09-02 15:47:00Z | 29166.50 | 29168.00 | 29157.00 | 29160.25 | 464 | NQ.v.0 |
| 2026-09-02 15:48:00Z | 29160.25 | 29161.25 | 29149.00 | 29151.50 | 709 | NQ.v.0 |

First 20 new rows: **n/a**

## 4. What was not done (on purpose)

- No rule redesign
- No P&L optimization
- No Phase72A/73/74/85 changes
- `phase58j/data/nq_continuous_1m_lw_extension.csv` **not overwritten**
- Existing CDX reports from the prior verdict **not replaced** except new alignment artifacts

## 5. How to finish this run on a machine that has the key

```bash
export DATABENTO_API_KEY=...   # do not commit
python3 -m cdx_research.python.extend_same_series
```

That writes `cdx_research/data/nq_continuous_1m_lw_extension_sep2026.csv` (new file).  
Continuity-audit that file against the Sep 2 tail **before** appending into `phase58j`.

## 6. Windows recovery continuation (same day)

Second runner: `python3 -m cdx_research.python.recover_windows`

- DATABENTO_API_KEY_PRESENT=false
- DATABENTO_AUTH=NOT_ATTEMPTED
- NinjaTrader CSV absent on this Mac
- SHA256 of unchanged `phase58j/data/nq_continuous_1m_lw_extension.csv`:
  `64be7aca625d0c67d7aa3e1fdc69089397f23452c47d0d0c3464d47dcf4d0f8b`
- Official MEDIUM alignment still 0/10
- Path B kit: `cdx_research/windows/Recover-CdxData.ps1` + `cdx_research/ninjatrader/CDXHistoricalBarExport.cs`

See `cdx_research/reports/WINDOWS_DATA_RECOVERY.md`.
