# Phase78 Causality Audit

- PREFIX_PASS: True
- PREFIX checked: 201
- PREFIX mismatches: 0

## Data audit
```json
{
  "symbol": "NQ.v.0",
  "continuous_method": "Databento GLBX.MDP3 volume continuous (NQ.v.0)",
  "bars": 3140775,
  "start_utc": "2017-10-01 17:00:00-05:00",
  "end_utc": "2026-09-02 10:48:00-05:00",
  "timezone_storage": "America/Chicago",
  "timezone_research": "America/New_York",
  "duplicate_bars": 0,
  "bad_ohlc": 0,
  "loaded_paths": [
    "/Users/anishalleti/CRT indicator/phase16/data/raw/nq_continuous_1m_oos_20171001_20201201.csv",
    "/Users/anishalleti/CRT indicator/phase18/data/raw/nq_continuous_1m_raw.csv",
    "/Users/anishalleti/CRT indicator/phase16/data/raw/nq_continuous_1m_20231201_20260626.csv",
    "/Users/anishalleti/CRT indicator/phase16/data/raw/nq_continuous_1m_postwindow_to_20260629T0000CT.csv",
    "/Users/anishalleti/CRT indicator/phase58j/data/nq_continuous_1m_lw_extension.csv"
  ]
}
```

**CAUSALITY_PASS:** True