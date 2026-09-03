# Phase58I — Management Forensics

## Canonical Population
Trades: 60,118 | M0 TotalR: 11,581

## Loss Classification

                       loss_type  count  pct_of_losses  avg_pre_exit_mfe  avg_post_exit_mfe  avg_mae     avg_r
                 WRONG_DIRECTION   1926       5.779445          0.022089           0.078819 2.116577 -1.379706
        RIGHT_DIRECTION_BAD_STOP  26683      80.069017          0.772750           7.596705 1.603880 -1.388060
  RIGHT_DIRECTION_TOO_EARLY_EXIT      3       0.009002          1.894061           2.784521 0.815465 -0.368442
RIGHT_DIRECTION_SLOW_DEVELOPMENT      8       0.024006          1.767002           0.567890 0.643674 -0.275178
                            CHOP   1112       3.336834          0.175543           0.546240 1.660945 -1.335991
                       AMBIGUOUS   3593      10.781695          1.591229           0.244065 1.649422 -1.307036

## Management Confusion Rate
Stop-outs later reaching +1R: 80.1% of losses

## Key Answers (Part A)
1. Wrong-direction losses: 5.8% of losses
2. Stop-related (bad stop): 80.1%
3. Time-exit related (too early): 0.0%
4. Pre-stop MFE buckets: see pre_stop_mfe.csv
5. Winner MAE before +1R: see winner_mae.csv
6. Time to favorable: see time_to_favorable.csv
7. Target extension: see target_forensics.csv
8. Management confusion large enough to investigate: **YES**

## H1 Rejected Population
 trades     avg_r     total_r  management_loss_like_pct  wrong_direction_like_pct
   1756 -0.331726 -582.510197                 76.947791                  7.068273
