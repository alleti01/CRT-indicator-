# CDX V3 Windows data recovery — 2026-09-21

Prior package verdict (preserved): `CDX_RE_INSUFFICIENT_INFORMATION`

This run verdict: **`CDX_RE_DATA_EXTENSION_FAIL`**

## Probe

- DATABENTO_API_KEY_PRESENT: `false`
- DATABENTO_AUTH: `NOT_ATTEMPTED`
- Host: this runner (do not print secrets)

## Data

- PATH: `NONE`
- SOURCE: none
- SYMBOL: 
- TIMEFRAME: 1m
- START: 
- END: unchanged
- ROWS: 0
- TIMEZONE: 
- CONTINUITY: N/A
- CANONICAL DATABENTO SERIES MODIFIED: `NO`
- SEPARATE CDX DATASET CREATED: `NO`
- SHA256 `phase58j/data/nq_continuous_1m_lw_extension.csv` (unchanged): `64be7aca625d0c67d7aa3e1fdc69089397f23452c47d0d0c3464d47dcf4d0f8b`

## Continuity detail

```
{
  "CONTINUITY_STATUS": "N/A"
}
```

## Labels

- HIGH=0 MEDIUM=10 LOW=26 (unchanged; no confidence upgrades)
- EXACT: 0
- ±1: 0
- AMBIGUOUS: 0
- UNMATCHED: 10
- ALIGNMENT GATE (>=7/10 EXACT or ±1): `FAIL`
- LONG MATCHED: 0
- SHORT MATCHED: 0
- LOW used for strict parity: NO

## Candidate V1

Scored: `NO`
Not scored (alignment gate failed or no series). Frozen rule untouched.

## Features / transition / state

Run: `NO`
Causality: `NOT RUN`

## TradingView file found on this Mac

Used for official parity: **NO**

```
{
  "present": true,
  "rows": 883,
  "first_et": "2026-09-21 07:18:00-04:00",
  "last_et": "2026-09-21 23:00:00-04:00",
  "volume": false,
  "used_for_parity": false,
  "medium_labels_in_window": 2,
  "hits": [
    {
      "label": "s01 LONG 22:13",
      "status": "EXACT_ON_TV_NQ1",
      "open": 30874.25,
      "high": 30874.75,
      "low": 30871.0,
      "close": 30872.75,
      "label_price": 30866.5
    },
    {
      "label": "s01 SHORT 22:25",
      "status": "EXACT_ON_TV_NQ1",
      "open": 30880.0,
      "high": 30881.0,
      "low": 30877.75,
      "close": 30880.5,
      "label_price": 30892.0
    }
  ],
  "reason_unused": "Not Databento and not NinjaTrader; 883 bars (~15h) cannot satisfy 7/10 MEDIUM gate"
}
```

## Production

Unchanged. Phase72A / 73 / 74 / 85 not modified. No SIM/funded routing.

## Next action

On the Windows trading PC, from the repo root:

```powershell
.\cdx_research\windows\Recover-CdxData.ps1
```

If Databento key is absent, add `CDXHistoricalBarExport` to an NQ 1-minute **ETH / electronic** chart with >= 30 days loaded, wait for export, re-run the script.
