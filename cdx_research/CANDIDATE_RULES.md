# Candidate rules

These are **behavioral hypotheses** from screenshots. They are **not** claimed to be CDX.

No rule was fit to P&L. No rule was scored against CDX bars because **zero labels matched research OHLCV**.

## Candidate V1 — local-extreme rejection

Implemented in `python/rules.py` (`apply_candidate_v1`).

```
LONG if
    near 20-bar low (close within 0.25 ATR of rolling low)
    AND lower_wick / range >= 0.35
    AND bullish close
    AND close in upper 45% of candle
    AND not same-direction signal in last 8 bars

SHORT if
    mirror at 20-bar high / upper wick / bearish close
```

Causal. Deterministic. Opposite side resets the same-direction cooldown.

Smoke (last 5 days of **pre-Sep-6** research data, unlabeled): **2 fires / 4141 bars**. Sparse, as a rare-signal rule should be. That is **not** CDX parity.

## Rejected for now

- RSI < 30 as a trigger: visually some longs are not oscillator-extreme; cannot test false-positive rate on CDX dates.
- EMA8/21 crossover alone: too common; would explode extras.
- HTF table gate: untrusted historically.

## Complexity cap

V1 is one family (reversal/rejection) + cooldown. Families 2–4 stay qualitative until bars exist.
