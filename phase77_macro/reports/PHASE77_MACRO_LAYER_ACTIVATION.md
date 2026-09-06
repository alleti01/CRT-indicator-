# Layer Activation

| State | Macro | Same-time | Baseline | Lift vs baseline |
|---|---|---|---|---|
| UPPER_REJECTION | 0.0000 | 0.0000 | 0.0000 | 1.00 |
| LOWER_REJECTION | 0.0000 | 0.0000 | 0.0000 | 1.00 |
| BUYING_ABSORBED_PROXY | 0.0000 | 0.0000 | 0.0000 | 1.00 |
| SELLING_ABSORBED_PROXY | 0.0000 | 0.0000 | 0.0000 | 1.00 |
| BUYING_INEFFICIENT | 0.0000 | 0.0011 | 0.0004 | 0.00 |
| SELLING_INEFFICIENT | 0.0000 | 0.0008 | 0.0009 | 0.00 |
| CONFIRMED_LONG | 0.0115 | 0.0117 | 0.0120 | 0.95 |
| CONFIRMED_SHORT | 0.0191 | 0.0163 | 0.0205 | 0.93 |

Macro bars: 262 | Same-time: 2,639 | Baseline: 5,499

Setup counts: {
  "MACRO": {
    "O5": 1
  },
  "MACRO_total": 1,
  "SAME_TIME_CONTROL": {
    "O6": 2
  },
  "SAME_TIME_CONTROL_total": 2,
  "ORDINARY_BASELINE": {
    "O6": 1
  },
  "ORDINARY_BASELINE_total": 1
}