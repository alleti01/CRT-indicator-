# Component Ablation (sampled windows)

          ablation      n  long_n  short_n   plus_1   plus_2  plus_2_5   mfe_15m   mae_15m  gross_avg_r                                                                   note
              FULL 6601.0  1345.0   5256.0 0.474308 0.299385  0.249077 19.465876 19.284957    -0.074923                                                                    NaN
       A1_NO_SWEEP    0.0     NaN      NaN      NaN      NaN       NaN       NaN       NaN          NaN                                            ENTRY_TIMING_NOT_COMPARABLE
A2_NO_DISPLACEMENT    NaN     NaN      NaN      NaN      NaN       NaN       NaN       NaN          NaN                  Phase78 funnel: 6814/6826 retain displacement vs FULL
         A3_NO_MSS    NaN     NaN      NaN      NaN      NaN       NaN       NaN       NaN          NaN Phase78 funnel: 6017/6814 retain MSS — largest drop after displacement
 A4_NO_FVG_RETRACE    NaN     NaN      NaN      NaN      NaN       NaN       NaN       NaN          NaN                                   Phase78 funnel: 3892/6017 retain FVG