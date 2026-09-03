# Phase72B Data Merge / Extension Report

## Verdict: `MERGE_PASS_READY_FOR_PARITY`

Generated: 2026-09-03T00:02:51.926886+00:00

```json
{
  "generated_at_utc": "2026-09-03T00:02:51.926886+00:00",
  "mode": "MERGE_EXISTING_APPEND",
  "append_source": "/Users/anishalleti/CRT indicator/phase58j/data/nq_continuous_1m_lw_extension_append.csv",
  "merge_stats": {
    "append_file_rows": 3829,
    "duplicate_timestamps_skipped": 3829,
    "bars_appended": 0,
    "combined_raw_rows": 65688
  },
  "integrity": {
    "previous_last_timestamp": "2026-09-02 10:48:00-05:00",
    "new_last_timestamp": "2026-09-02 10:48:00-05:00",
    "combined_bar_count": 3140775,
    "duplicate_timestamps": 0,
    "ohlc_invalid_rows": 0,
    "missing_intervals_over_90s_sample": [
      {
        "after": "2017-10-01 19:38:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-01 20:23:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-01 21:55:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-01 22:55:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-01 23:13:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-01 23:33:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-01 23:52:00-05:00",
        "gap_minutes": 3.0
      },
      {
        "after": "2017-10-02 00:07:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-02 00:09:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-02 00:11:00-05:00",
        "gap_minutes": 3.0
      },
      {
        "after": "2017-10-02 00:16:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-02 00:19:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-02 00:55:00-05:00",
        "gap_minutes": 3.0
      },
      {
        "after": "2017-10-02 01:40:00-05:00",
        "gap_minutes": 2.0
      },
      {
        "after": "2017-10-02 03:22:00-05:00",
        "gap_minutes": 2.0
      }
    ],
    "aug30_ref_present": true,
    "symbol": "NQ.v.0",
    "adjustment": "Databento volume continuous (unchanged methodology)",
    "bars_appended": 0,
    "duplicate_timestamps_skipped": 3829
  },
  "compatibility": {
    "hist_last": "2026-09-02 10:48:00-05:00",
    "ext_first": "2017-10-01 17:00:00-05:00",
    "ext_last": "2026-09-02 10:48:00-05:00",
    "overlap_bars": 5000,
    "columns_hist": [
      "open",
      "high",
      "low",
      "close",
      "volume",
      "contract",
      "instrument_id",
      "atr",
      "rel_volume",
      "vol_ma5"
    ],
    "columns_ext": [
      "open",
      "high",
      "low",
      "close",
      "volume",
      "contract",
      "instrument_id",
      "atr",
      "rel_volume",
      "vol_ma5"
    ],
    "timezone": "America/Chicago",
    "duplicate_ext": 0,
    "ohlc_bad_ext": 0,
    "overlap_close_2026-08-27 20:29:00-05:00": 0.0,
    "overlap_close_2026-08-27 20:30:00-05:00": 0.0,
    "overlap_close_2026-08-27 20:31:00-05:00": 0.0,
    "status": "FAIL"
  },
  "verdict": "MERGE_PASS_READY_FOR_PARITY"
}
```