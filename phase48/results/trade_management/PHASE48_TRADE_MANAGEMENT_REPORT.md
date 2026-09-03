# Phase 48 — Trade Management Research

## Executive Summary

Phase48 tested exit/stop/target/management variants on the **frozen Phase45 B1 entry population** (N=1135). Entry selection was not modified.

### Primary Results

           MODEL    N      AvgR        PF      TotalR     MaxDD  WinRate      MAE      MFE  MFE_Capture   AvgHold
      M0_Control 1135  1.648373 17.775735 1870.903510  8.385997 0.866079 0.189103 0.270835          NaN       NaN
         Stop_S3 1135 -0.000250  0.999630   -0.284189 78.799164 0.328634 0.975536 1.368303          NaN       NaN
    Fixed_Target 1135  0.350991  3.890709  398.374723 12.721714 0.685463 0.225172 0.295859    86.149100 35.884581
      Break_Even 1135  1.634303 20.369521 1854.933781  7.373477 0.885463 0.176485 0.244675   606.474555 11.161233
        Partials 1135  1.632305 18.049728 1852.666408  8.385997 0.869604 0.189103 0.270835   606.467647 12.103084
    Opposite_BOS 1135  1.636356 18.739099 1857.263668  7.303966 0.872247 0.182748 0.249308   606.470599 11.303084
       Time_Exit 1135  1.645479 17.678001 1867.618509  8.385997 0.866079 0.189103 0.270344   606.467810 12.042291
      Stagnation 1135  1.558415 21.778400 1768.800835  9.519122 0.840529 0.146812 0.218853   606.401483  6.406167
     Profit_Lock 1135  1.639173 18.282942 1860.461784  8.385997 0.868722 0.187501 0.256686   606.470278 11.940088
Structure_Target 1135  0.418653  4.525213  475.171498 14.261784 0.689868 0.222963 0.284803    86.210641 35.074009
         INV_15M 1135  1.635478 21.947674 1856.267121  4.024790 0.851982 0.151392 0.228227   606.554332  9.237885
        Trailing 1135  1.633738 18.918296 1854.292343  7.243522 0.874009 0.182377 0.239098    -0.318120 11.059912

### Incremental vs M0 Control

           MODEL     dAvgR        dPF      dTotalR    dMaxDD  dWinRate  dMFE_Capture  dAvgHold
         Stop_S3 -1.648624 -16.776105 -1871.187699 70.413167 -0.537445           NaN       NaN
    Fixed_Target -1.297382 -13.885026 -1472.528787  4.335717 -0.180617           NaN       NaN
      Break_Even -0.014070   2.593786   -15.969729 -1.012521  0.019383           NaN       NaN
        Partials -0.016068   0.273993   -18.237103  0.000000  0.003524           NaN       NaN
    Opposite_BOS -0.012017   0.963363   -13.639842 -1.082031  0.006167           NaN       NaN
       Time_Exit -0.002894  -0.097734    -3.285001  0.000000  0.000000           NaN       NaN
      Stagnation -0.089958   4.002665  -102.102675  1.133125 -0.025551           NaN       NaN
     Profit_Lock -0.009200   0.507207   -10.441726  0.000000  0.002643           NaN       NaN
Structure_Target -1.229720 -13.250522 -1395.732012  5.875787 -0.176211           NaN       NaN
         INV_15M -0.012895   4.171938   -14.636389 -4.361208 -0.014097           NaN       NaN
        Trailing -0.014635   1.142561   -16.611167 -1.142475  0.007930           NaN       NaN

## Key Findings

- **M0 control** exactly reproduces Phase45 B1 management (AvgR=1.648, PF=17.78, TotalR=1871).
- **ATR/structure stop changes (Stop_S3)** destroyed expectancy — normalized 1R stops with retargeted exits did not improve OOS.
- **Lower fixed-R targets** increased win rate but reduced TotalR materially.
- **Break-even, partials, opposite BOS, time exit, stagnation, profit-lock, 15M invalidation** all reduced or failed to improve TotalR vs M0.
- **Trailing** was tested but must pass sanity checks; any anomalous R inflation is rejected.

## Final Assessment

PHASE44 PARITY: PASS

PHASE45 ENTRY PARITY: PASS

CANONICAL ENTRY COUNT: 1135

CONTROL MANAGEMENT:
N = 1135
AvgR = 1.648
PF = 17.78
TotalR = 1870.9
MaxDD = 8.39
WinRate = 86.6%
MFE Capture = N/A
AvgHold = N/A

BEST STOP MODEL: NONE

BEST TARGET MODEL: NONE

BEST EXIT MODEL: NONE

BEST OVERALL MANAGEMENT MODEL: M0 CONTROL

OOS INCREMENTAL VALUE: No family demonstrated credible positive ΔTotalR with matched entries.

DOES NEW STOP PLACEMENT IMPROVE CONTROL: NO

DOES NEW TARGET LOGIC IMPROVE CONTROL: NO

DOES BREAK-EVEN IMPROVE CONTROL: NO

DO PARTIALS IMPROVE CONTROL: NO

DOES TRAILING IMPROVE CONTROL: NO

DOES OPPOSITE 1M BOS EXIT IMPROVE CONTROL: NO

DOES 15M INVALIDATION IMPROVE CONTROL: NO

DOES TIME-BASED EXIT IMPROVE CONTROL: NO

DOES STAGNATION EXIT IMPROVE CONTROL: NO

DOES PROFIT-LOCK / GIVEBACK MANAGEMENT IMPROVE CONTROL: NO

DOES ANY MANAGEMENT CHANGE IMPROVE LONGS: NO

DOES ANY MANAGEMENT CHANGE IMPROVE SHORTS: NO

IS THE BEST RESULT ROBUST ACROSS 2024/2025/2026: NO

IS THE BEST RESULT ROBUST ACROSS WALK-FORWARD FOLDS: NO

IS PARAMETER SELECTION STABLE: YES

SHOULD PHASE45 B1 ENTRY CHANGE: NO

SHOULD PHASE44 CHANGE: NO

SHOULD TRADE MANAGEMENT CHANGE: NO

READY FOR PINE: NO — forward paper validation required first

MOST IMPORTANT FINDING:
On identical Phase45 B1 entries, alternative stops, targets, break-even, partials, trailing, structure exits, time exits, and stagnation rules did not produce stable stitched walk-forward OOS improvement in TotalR over the existing frozen stop/target/time management. Lower targets and stop geometry changes often removed the edge; break-even and partials increased scratches without improving expectancy.

NEXT STEP:
Keep existing Phase45 trade management (M0) unchanged. Proceed to forward paper validation of Phase44 + Phase45 B1 entry + current exit stack.