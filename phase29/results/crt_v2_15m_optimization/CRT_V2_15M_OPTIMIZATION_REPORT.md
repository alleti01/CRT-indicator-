# CRT V2 @ 15m Focused Optimization Report

**Classification: A — STRONG 15M TRADE ARCHITECTURE** *(9/10 success criteria; WF N=110 below 150 preferred gate)*

**Ready for Pine:** Conditional — economics strong; expand validation sample before live deployment.

---

## Baseline parity (Phase 28 reproduced)

| Metric | Phase 28 | Phase 29 |
|---|---:|---:|
| N | 210 | 210 |
| Net AvgR | +0.094R | +0.094R |
| Net TotalR | +20.0R | +19.8R |
| Net PF | 1.31 | 1.31 |
| MaxDD | 5.6R | 5.6R |

Frozen signal generation unchanged. Execution = confirmation close, 1.5 ATR stop, 2R target, 60m hold.

---

## Key findings

1. **BOS-level retest entry** (max 2 bars, 67.6% fill) improves net economics on matched signals (+0.17R AvgR vs CURRENT on N=142 overlap).
2. Walk-forward **unanimously** selects: **BOS_RETEST + 0.75–1.25 ATR stop + 3R target + 60m hold + FIXED** (7/7 folds).
3. **Stitched walk-forward:** N=110, Net AvgR **+0.325R**, PF **1.89**, MaxDD **5.1R** — materially above baseline.
4. Baseline **long/short asymmetry persists** (Long PF 1.59 vs Short PF 0.94), but WF shorts also contribute (N=40, +0.41R AvgR) on smaller sample.
5. **Management overlays** (BE, partials, trail) do not beat FIXED on this signal set.

---

## Walk-forward vs in-sample

In-sample grid best (BOS_RETEST, 0.75 stop, 3R, 45m): +0.28R AvgR on N=142 — optimistic.

Stitched WF is the primary result: **+0.325R AvgR**, survives 1.5×/2.0× costs and outlier removal.

---

## Next step

**Phase 30:** Implement frozen CRT V2-B signal + WF-selected execution (BOS retest entry, 0.75–1.25 ATR stop, 3R target, 60m hold) in Pine for visual validation. Hold production SHORT-only ablation for a future preregistered test.
