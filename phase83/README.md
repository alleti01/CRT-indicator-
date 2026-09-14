# Phase83 — NQ Premarket / Overnight Breakout Acceptance

Independent research. **Does not modify** Phase72A, ledger, Phase73, Phase74, webhooks, NinjaTrader, or M0.

## Hypothesis

After a **predefined** overnight/premarket high or low is frozen at 09:29 ET, does **confirmed acceptance or rejection** outside that level contain directional information in the 09:30–11:00 ET window?

This is **not** a Phase72A reproduction and does **not** use Phase72B as ground truth.

## Method (causal)

1. Freeze ON high/low from 18:00 previous trading day through 09:29 ET.
2. Record prior completed RTH high/low/close (09:30–16:00 ET).
3. Detect first touch / first confirmation per side (opportunity memory).
4. Enter only after the confirmation rule’s last required bar has **completed**.
5. Manage every primary comparison with frozen M0 (1.0R / 2.5R / 60m / STOP_FIRST).
6. Controls: random direction, flipped direction, timing-matched, alternate levels.
7. Chronological 60/20/20 by **session date**.
8. Prefix-invariance audit on overnight freeze, 2M aggregation, and decisions.

## Run

```bash
python3 phase83/diagnostics/run_phase83.py
```

Outputs: `phase83/reports/` and `phase83/checkpoints/`.

## Verdicts

See `reports/PHASE83_FINAL_REPORT.md`. A PASS still does **not** authorize production changes.
