# Entry Timing + Static/Chop Precision Report

## Parity
{'counts': {'L': 2075, 'S': 1836, 'RL': 976, 'RS': 925, 'total': 5812}, 'parity_pass': True}

## Behavior rates (post-hoc diagnostic)
{
  "IMMEDIATE_EXPANSION": 0.39160357880247765,
  "CLEAN_WINNER": 0.2789057123193393,
  "WRONG_DIRECTION": 0.2255677907777013,
  "DELAYED_EXPANSION": 0.08706125258086717,
  "STATIC_CHOP": 0.01686166551961459
}

## Baseline performance
- N: 5812
- AvgR: +0.229R
- PF: 1.48

## Walk-forward expansion model
- Mean AUC (ExtraTrees): 0.699
- Top features: impulse_3bar, directional_efficiency, pre_entry_move_3_atr, price_vs_ema8, body_atr

## Best filter (OOS stitched)
{
  "type": "p_expansion_et",
  "threshold": 0.47324241322692023,
  "description": "Keep if ExtraTrees expansion probability >= 0.473",
  "baseline": {
    "N": 4271,
    "WinRate": 0.4827909154764692,
    "AvgR": 0.2708933115076147,
    "TotalR": 1156.9853334490224,
    "PF": 1.6008157031522467,
    "MaxDD": 12.799129585796095,
    "ReturnMaxDD": 90.39562617859525
  },
  "filtered": {
    "N": 2776,
    "WinRate": 0.5417867435158501,
    "AvgR": 0.44199711843753325,
    "TotalR": 1226.9840007825924,
    "PF": 2.123686737886239,
    "MaxDD": 10.464722782894796,
    "ReturnMaxDD": 117.24954652293033
  },
  "retention": 0.6499648794193398
}

## Static exit best rule
{
  "rule": "FROZEN",
  "N": 5812.0,
  "WinRate": 0.4803854094975912,
  "AvgR": 0.27202599029322233,
  "TotalR": 1581.0150555842083,
  "PF": 1.5975568399914861,
  "MaxDD": 12.799129585796209,
  "ReturnMaxDD": 123.52520106826127
}

## Classification
**A** — causal entry filter improves walk-forward OOS expectancy; timing shifts and early exits do not.

## Deployable Pine candidate (simple 1-condition rule)
Walk-forward train Q35 on `impulse_3bar = abs(close-close[3])/ATR`:
- OOS retention ~65% (2,773 / 4,271 stitched test signals)
- OOS net AvgR **+0.352R** vs baseline **+0.242R** (+0.11R)
- OOS net PF **1.79** vs **1.52**
- Fixed threshold proxy **0.65 ATR** yields similar retention/expectancy

**Phase 40 recommendation:** reject entry when `impulse_3bar < 0.65` at the signal bar (do not delay entry bar; do not add early-exit logic).

## Entry timing (causal alternatives)
| Variant | AvgR (gross path) |
|---------|-------------------|
| CURRENT | +0.272R |
| NEXT_OPEN | +0.122R |
| NEXT_CLOSE | -0.083R |

Frozen retest entry timing is optimal among tested causal alternatives.

## Early no-movement exit
All preregistered static-exit rules underperform or match **FROZEN** max-hold on net path metrics.

## Audit
Lookahead: PASS | Deterministic: PASS
