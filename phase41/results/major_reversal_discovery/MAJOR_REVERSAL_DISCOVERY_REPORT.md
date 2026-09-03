# Major Reversal Discovery Report

## Primary opportunity label
2R_before_1R_90m

## Capture summary
{
  "total": 3892,
  "bullish": 1961,
  "bearish": 1931,
  "pct_phase33": 0.1736896197327852,
  "pct_phase40": 0.1736896197327852,
  "pct_missed": 0.4493833504624872,
  "bull_missed_pct": 0.43090260071392145,
  "bear_missed_pct": 0.4681512169860176
}

## Best causal trigger
{
  "name": "EXTENSION_REJECTION_RECLAIM",
  "description": "6-bar extension + rejection wick + reclaim/micro-structure + EMA20 stretch (walk-forward thresholds)",
  "bull_conditions": [
    "ret_6_atr <= train_q75",
    "lower_wick >= train_q25",
    "close_loc >= 0.52",
    "reclaim_or_higher_low",
    "dist_ema20 <= train_q70"
  ],
  "bear_conditions": [
    "ret_6_atr >= train_q25",
    "upper_wick >= train_q25",
    "close_loc <= 0.48",
    "lower_high_or_fail_reclaim",
    "dist_ema20 >= train_q30"
  ]
}

## OOS performance (stitched walk-forward)
{
  "N": 13047,
  "WinRate": 0.38821184946731047,
  "AvgR": -0.09141992566827797,
  "TotalR": -1192.7557701940227,
  "PF": 0.8370354202912128,
  "MaxDD": 1207.236803953996,
  "ReturnMaxDD": -0.988004810893319
}

## Incremental overlap
[
  {
    "segment": "OVERLAP",
    "N": 438,
    "WinRate": 0.3584474885844749,
    "AvgR": -0.1418383650708026,
    "TotalR": -62.12520390101154,
    "PF": 0.7502074874613418,
    "MaxDD": 67.21932711445959,
    "ReturnMaxDD": -0.9242163908488121
  },
  {
    "segment": "NEW_PHASE41_ONLY",
    "N": 12609,
    "WinRate": 0.38924577682607664,
    "AvgR": -0.08966853567237777,
    "TotalR": -1130.6305662930113,
    "PF": 0.8400896639854104,
    "MaxDD": 1145.1116000529819,
    "ReturnMaxDD": -0.987354041510626
  }
]

## Combined system
               system      N   WinRate      AvgR       TotalR        PF        MaxDD  ReturnMaxDD
0  CURRENT_FROZEN_P40   3680  0.411413  0.026128    96.149775  1.047862    50.450930     1.905808
1            P41_ONLY  13047  0.388212 -0.091420 -1192.755770  0.837035  1207.236804    -0.988005
2            COMBINED  16727  0.393316 -0.065559 -1096.605995  0.882439  1242.221260    -0.882778

## Classification
**D**
