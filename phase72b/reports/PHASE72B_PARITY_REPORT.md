# Phase72B Parity Report

## Verdict: `MANUAL_PARITY_IN_PROGRESS`

Generated: 2026-09-02T23:36:22.734775+00:00

## Frozen sources

| Artifact | Hash |
|----------|------|
| Pine (`phase72a_autonomous_trader.pine`) | `7c38c6dbcc811683` |
| Python mirror (`phase72b/python/*`) | `13c6f0ebf55e8936` |

## Window

- **Label:** aug28_session
- **Bars:** 3136391 .. 3136946 (555 event rows)
- **Runtime:** 21.33s

## Python mirror event counts

```json
{
  "signals_long": 5,
  "signals_short": 8,
  "entries_long": 5,
  "entries_short": 8,
  "exits_stop": 11,
  "exits_target": 1,
  "exits_time": 0
}
```

## Ground truth rule

Ground truth is **actual TradingView autonomous trader behavior**, exported via Phase72B diagnostic plots.
`phase72a_python_review_ghosts.pine` is **display-only** and must not define expected events.

## TV reference status

NO_TV_REFERENCE: Place machine-readable TV export at `phase72b/diagnostics/tv_event_log.csv`.

Enable **Phase72B export** in Pine (`exportParity` input), load on NQ1! 1M, export Data Window CSV for overlap window.

## Prefix invariance (causality)

```json
{
  "pass": true,
  "skipped": true
}
```

## Restart test

```json
{
  "pass": null,
  "skipped": true
}
```

## Next steps for PASS

1. Export TV reference events for test windows (Aug 26 priority)
2. Run OHLC parity check (TV vs LW local) — stop on `DATA_SERIES_MISMATCH`
3. First-divergence loop: T-10..T+10 forensic window, fix root cause only, full rerun
4. Require 100% SIGNAL / ENTRY / EXIT / STATE parity before `PHASE72B_PARITY_PASS`

## Known audit items (Phase72B checklist)

- HTF bucket timing: developing HTF via `phase60/python/developing_htf.py`
- ATR: SMA(range,14) + `f_atrUse` fallback (not RMA)
- Cooldown: no decrement on exit bar (`p58SkipCooldownDec`)
- Entry: signal bar T, entry open T+1
- Phase71 STOP_FIRST same-bar stop+target
- Confidence/P4/H1: simplified port — verify against Pine on first divergence

