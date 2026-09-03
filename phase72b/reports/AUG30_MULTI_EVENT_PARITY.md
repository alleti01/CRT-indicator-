# Aug 30 Multi-Event Parity

## Verdict: `FIRST_NEW_DIVERGENCE_FOUND`

Session: 2026-08-30 17:00:00-05:00 .. 2026-08-30 22:00:00-05:00 Chicago

### Parity levels (TV reference events)

- **OHLC**: PASS
- **ATR**: PASS
- **FEATURE**: FAIL
- **STATE**: FAIL
- **SIGNAL**: PASS
- **ENTRY**: FAIL
- **EXIT**: PASS

### Prefix invariance

```json
{
  "reference_start": 3136946,
  "reference_ts": "2026-08-30 17:00:00-05:00",
  "prefixes": [
    {
      "start_i": 3136946,
      "start_ts": "2026-08-30 17:00:00-05:00",
      "bars_checked": 301,
      "mismatches": 0,
      "first": null,
      "pass": true
    },
    {
      "start_i": 3136446,
      "start_ts": "2026-08-28 07:40:00-05:00",
      "bars_checked": 301,
      "mismatches": 15,
      "first": {
        "bar_index": 3136947,
        "column": "signal_long",
        "prefix_start": 3136446
      },
      "pass": false
    },
    {
      "start_i": 3133946,
      "start_ts": "2026-08-26 12:00:00-05:00",
      "bars_checked": 301,
      "mismatches": 15,
      "first": {
        "bar_index": 3136947,
        "column": "signal_long",
        "prefix_start": 3133946
      },
      "pass": false
    }
  ],
  "pass": false
}
```

### First failure (chronological)

```json
{
  "event_id": "OBS-AUG30-003",
  "timestamp": "2026-08-30 20:35:00-05:00",
  "event_type": "ENTER_SHORT",
  "direction": "SHORT",
  "tv_ohlc": 29310.75,
  "python_ohlc": 29310.75,
  "ohlc_pass": true,
  "tv_atr": 14.7679,
  "python_atr": 14.767857142857142,
  "atr_pass": true,
  "tv_state": "SHORT_ACTIVE",
  "python_state": "COOLDOWN",
  "state_pass": false,
  "tv_evidence": 7,
  "python_evidence": 8,
  "evidence_pass": false,
  "tv_signal": false,
  "python_signal": false,
  "signal_pass": true,
  "tv_entry": true,
  "python_entry": false,
  "entry_pass": false,
  "tv_exit": false,
  "python_exit": false,
  "exit_pass": true,
  "tv_price": 29312.5,
  "python_price": "",
  "price_pass": false,
  "first_divergence": "FEATURES:evidence tv=7 py=8",
  "status": "FAIL"
}
```

### Minimum stable warmup (Aug 30)

**2026-08-30 17:00:00-05:00** (session open after weekend gap). Prefixes starting before this bar diverge at session open (expected).

### Short trace window (20:46)

PASS=True

**MORE_TV_REFERENCE_REQUIRED** — only Aug 30 screenshot observations exist in `manual_tv_observations.csv`.

Python session exit coverage: EXIT_STOP=True, EXIT_TARGET=True (TV confirms STOP only via OBS-AUG30-004).