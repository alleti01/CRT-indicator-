# Phase58G — Confidence Calibration Forensics

## Why HIGH Underperforms

Phase58F HIGH band: **19,324 trades**, AvgR **-0.091**, TotalR **-1,763**

VERY_HIGH requires score ≥4. HIGH is score 2–3. Most HIGH trades are **active-aligned + structure-aligned but missing the fourth confirming point** (HTF support or countertrend-weak bonus). They look almost-confident but lack full alignment.

## HIGH Subtype Split (zero delay, causal)

   high_subtype  count  pct_of_high  win_rate      AvgR       PF       TotalR
     HIGH_CLEAN     26     0.134548  0.307692 -0.358104 0.627551    -9.310707
  HIGH_REVERSAL   5669    29.336576  0.428471  0.156040 1.201241   884.592533
HIGH_CONFLICTED  13629    70.528876  0.336562 -0.193543 0.788051 -2637.800682

| Subtype | Meaning |
|---------|---------|
| **HIGH_CONFLICTED** | Active + structure aligned, no HTF/CT confirm — "almost VERY_HIGH" trap |
| **HIGH_REVERSAL** | Active opposed + moderate/strong reversal support — legitimate countertrend |
| **HIGH_CLEAN** | Residual (tiny) |

## Conflict Type Breakdown

                 conflict_type  count  pct_of_high      AvgR       TotalR  win_rate
active_aligned_missing_confirm  13629    70.528876 -0.193543 -2637.800682  0.336562
            ambiguous_reaction  13575    70.249431 -0.196723 -2670.509597  0.335838
                 good_location  10290    53.249845 -0.004593   -47.259345  0.391254
                 weak_location   9034    46.750155 -0.189867 -1715.259510  0.331857
                active_opposed   5673    29.357276  0.156289   886.627019  0.428521
          htf_ltf_disagreement   5236    27.095839  0.128103   670.744759  0.419595
             htf_contradiction   1778     9.200994 -0.334002  -593.855390  0.290776

## Top Feature Combos in HIGH

                feature_combo  count    high_subtype      AvgR       TotalR  win_rate
ACT_ALN+STR_ALN+HTF0+UNCE+STR   6132 HIGH_CONFLICTED -0.005321   -32.628275  0.378343
ACT_ALN+STR_ALN+HTF0+UNCE+MOD   4981 HIGH_CONFLICTED -0.327744 -1632.491891  0.310179
ACT_OPP+STR_ALN+HTF++REVE+STR   3456   HIGH_REVERSAL  0.365543  1263.315042  0.485822
ACT_OPP+STR_ALN+HTF0+REVE+STR   2213   HIGH_REVERSAL -0.171135  -378.722509  0.338906
ACT_ALN+STR_ALN+HTF-+UNCE+STR   1099 HIGH_CONFLICTED -0.105574  -116.025366  0.342129
ACT_ALN+STR_ALN+HTF0+UNCE+WEA    709 HIGH_CONFLICTED -0.597302  -423.487450  0.259520
ACT_ALN+STR_ALN+HTF-+UNCE+MOD    590 HIGH_CONFLICTED -0.704388  -415.589117  0.206780

## Score Breakdown within HIGH

 score  count      AvgR      TotalR  win_rate
     2   3971 -0.241874 -960.483328  0.317804
     3  15353 -0.052240 -802.035528  0.375301

## Band Recalibration (relabel only — 100% trade retention)

Demote `missing_vh_confirm` HIGH → MEDIUM:

     band  count  win_rate      AvgR       PF       TotalR
VERY_HIGH  34608  0.475439  0.293748 1.405687 10166.034761
     HIGH   5695  0.427919  0.153693 1.197997   875.281826
   MEDIUM  17021  0.366253 -0.090303 0.896688 -1537.055645
      LOW   3164  0.488306  0.374186 1.544539  1183.925268
 VERY_LOW   1465  0.445051  0.182238 1.238602   266.979307

Original monotonicity: **FAIL**
Recalibrated monotonicity: **FAIL**

## Shadow Abstention (diagnostic — P4 unchanged)

                      policy  abstained  abstained_AvgR  abstained_TotalR  kept_AvgR  kept_TotalR  winners_retained_pct  losers_removed_pct  selectivity_ratio
     ABSTAIN_HIGH_CONFLICTED      13629       -0.193543      -2637.800682   0.281288 13592.966200             83.211332           26.109555           1.268953
ABSTAIN_CONFLICTED_UNCERTAIN      13571       -0.196931      -2672.544082   0.281669 13627.709600             83.321133           26.028703           1.274408
                 P4_BASELINE         79       -0.553878        -43.756395   0.177763 10998.921913             99.934119            0.176143           2.093305

## Answers

1. **Dominant feature combinations:** `ACT_ALN+STR_ALN+HTF0+UNCE+*` (13,629 trades, AvgR -0.194). Active-aligned + structure-aligned without HTF/CT confirmation in UNCERTAIN market state.

2. **Conflict categories:**
   - **Incomplete confirmation (70.5%):** active+struct missing VH confirm — primary pathology
   - **Legitimate reversals (29.3%):** active opposed + reversal support — positive expectancy
   - **HTF contradiction (9.2%):** negative
   - **Ambiguous reaction / UNCERTAIN (70.2%):** co-occurs with conflicted archetype
   - **Weak reversal attempts:** small but very negative
   - **Location:** good-location conflicted trades still negative

3. **Can HIGH split into HIGH_CLEAN / HIGH_CONFLICTED without delay?** **Yes.** Causal flags already available at T0. Split is `70.5%` CONFLICTED / `29.3%` REVERSAL / remainder CLEAN.

4. **Does HIGH_CONFLICTED have reliably negative shadow expectancy?** **Yes.** AvgR -0.194, TotalR -2,638. Abstaining all HIGH_CONFLICTED yields abstained AvgR -0.194.

5. **Can calibration improve without losing winner retention?** **Partially.**
   - **Band relabel (recalibration):** 100% winner retention — fixes HIGH band (+0.154 recal HIGH) but MEDIUM absorbs garbage; full monotonicity still fails.
   - **Abstention:** HIGH_CONFLICTED abstention removes 26.1% losers but destroys 16.8% winners — too aggressive for production.
   - **Recommendation:** Use HIGH_CONFLICTED as a **display/diagnostic sub-band**; keep P4 as the only abstention policy. Future Phase58H could test surgical abstention on CONFLICTED+HTF-contra only (~1,778 trades).

## Verdict

HIGH PATHOLOGY IDENTIFIED: PASS
HIGH_CONFLICTED SPLIT VALID: PASS
HIGH_CONFLICTED NEGATIVE EXPECTANCY: PASS
HIGH_REVERSAL POSITIVE EXPECTANCY: PASS
RECALIBRATION IMPROVES HIGH BAND: PASS
FULL MONOTONICITY AFTER RECAL: FAIL
ABSTAIN HIGH_CONFLICTED WINNER SAFE: FAIL
P4 UNCHANGED: PASS
PHASE58F UNCHANGED: PASS
PHASE58G OVERALL: PASS
