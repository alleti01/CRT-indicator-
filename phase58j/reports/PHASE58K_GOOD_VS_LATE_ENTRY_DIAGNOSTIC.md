# PHASE58K — ENTRY QUALITY DIAGNOSTIC

Diagnostic only. No strategy logic, parameters, or filters changed.

## Frozen config intact: PASS

## Last-week M1 outcomes (verified)

| Outcome | N |
|---------|---|
| TARGET | 55 |
| STOP | 71 |
| TIME | 0 |

---

## Top features separating M1 TARGET vs STOP (last week)

Ranked by |Cohen's d| (practical separation, not p-values).

| Rank | Feature | Cohen's d | TARGET mean | STOP mean |
|------|---------|-----------|-------------|-----------|
| 1 | m5_move_atr | -0.57 | -0.43 | +0.98 |
| 2 | dist_20_ext_atr | -0.55 | -1.54 | -0.91 |
| 3 | move_20_atr | -0.51 | +0.56 | +1.62 |
| 4 | dist_10_ext_atr | -0.39 | -0.78 | -0.55 |
| 5 | dist_pullback_ext_atr | -0.35 | +2.64 | +3.04 |
| 6 | prior_bar_range_atr | +0.30 | +1.13 | +1.01 |
| 7 | m15_move_atr | +0.27 | +2.07 | +1.39 |
| 8 | dist_5_ext_atr | -0.24 | -0.61 | -0.48 |
| 9 | reaction_score | -0.23 | 1.78 | 1.92 |
| 10 | bars_since_swing | +0.22 | 5.05 | 4.42 |

**Interpretation:** Winners tend to have **less prior extension** into the trade (lower direction-adjusted 5m/10m/20m moves, more negative dist-from-extreme = closer to or past recent highs for shorts). Stops cluster with **already-extended** entries (+1 ATR 5m move vs -0.4 for targets).

---

## LW-063194 (#9) vs LW-063196 (#11)

| Feature | #9 (TARGET) | #11 (STOP) | Difference |
|---------|-------------|------------|------------|
| move_10_atr | **3.76** | 1.08 | +2.68 |
| move_5_atr | 2.28 | 1.57 | +0.70 |
| m15_move_atr | **8.49** | 1.93 | +6.56 |
| m5_move_atr | 0.00 | **2.62** | -2.62 |
| dist_10_ext_atr | **0.00** (at extreme) | -0.08 | +0.08 |
| same_dir_streak | **6** | 2 | +4 |
| 15m_context | BEARISH | NEUTRAL | — |
| market_state | UNCERTAIN | UNCERTAIN | — |

**Archetype labels:** Both → CHOP (market_state=UNCERTAIN fires before extension rules).  
**Descriptive read:** #9 is a **SHORT at the 10-bar low** (dist_10=0) with strong 15m/10m downside extension already in place — visually "early continuation." #11 is **less extended on 10m** but **more extended on 5m**, entered in **NEUTRAL 15m** context vs BEARISH for #9.

**Key causal differences at entry:**
1. #9 at recent 10-bar extreme; #11 slightly inside range  
2. #9 much larger 15m/10m directional move already delivered  
3. #9 BEARISH 15m vs #11 NEUTRAL 15m  
4. #9 longer same-direction streak (6 vs 2)

---

## Extension / chase analysis

`move_10_atr` deciles (last week) — **non-monotonic**; decile 8 worst (15% target rate), deciles 2/5/6 best (~62%).

| Decile | N | Target rate | M1 AvgR |
|--------|---|-------------|---------|
| 1 (low ext) | 13 | 38% | +0.35 |
| 8 (high ext) | 13 | **15%** | -0.46 |
| 10 (highest) | 13 | 46% | +0.62 |

**Verdict: WEAK / INCONSISTENT** on last week alone. High extension is dangerous in mid-deciles but not uniformly.

---

## Opportunity age

All 126 last-week entries have **bars_since_opp_start = 1** (single-bar opportunity age at take). No spread across buckets — **cannot assess age effect last week**.

---

## Loser forensics (71 M1 stops)

| Cause | N | AvgR |
|-------|---|------|
| LATE_EXTENSION | 47 | -1.00 |
| CHOP | 17 | -1.00 |
| WRONG_DIRECTION | 5 | -1.00 |
| EARLY_BUT_FAILED | 2 | -1.00 |

66% of stops tagged **LATE_EXTENSION** by entry-time rules (move_10 ≥ 1.5 ATR or extended archetype).

---

## Winner retention sweep (m5_move_atr — top separator)

Excluding top 10% most-extended 5m moves: 13 trades out, 9 losers / 4 winners, **92.7% winner retention**.  
Excluding top 30%: 26 losers out, **78% retention**.

**No single feature cleanly removes many losers while keeping most winners** at practical quantile cuts.

---

## Historical stability (60,118 canonical H1 trades, same frozen M1)

7/10 top features show **same sign** of Cohen's d as last week for extension metrics.  
**MIXED** overall — `prior_bar_range_atr`, `reaction_score`, `bars_since_swing` flip sign vs last week.

Extension direction agrees historically: higher prior move → worse outcomes (negative d for move_20, dist_20, m5_move).

---

## Archetype rules

See `phase58k/reports/PHASE58K_ARCHETYPE_RULES.txt`

---

## Output files

- `phase58j/results/phase58k_entry_diagnostics.csv`
- `phase58j/results/phase58k_feature_comparison.csv`
- `phase58j/results/phase58k_extension_deciles.csv`
- `phase58j/results/phase58k_opportunity_age.csv`
- `phase58j/results/phase58k_archetypes.csv`
- `phase58j/results/phase58k_context_interaction.csv`

---

## FINAL REPORT

```
PHASE58K — ENTRY QUALITY DIAGNOSTIC

FROZEN CONFIG INTACT: PASS

LAST-WEEK TRADES:
TARGET: 55
STOP: 71
TIME: 0

TOP 10 FEATURES SEPARATING TARGET VS STOP:
1. m5_move_atr (d=-0.57)
2. dist_20_ext_atr (d=-0.55)
3. move_20_atr (d=-0.51)
4. dist_10_ext_atr (d=-0.39)
5. dist_pullback_ext_atr (d=-0.35)
6. prior_bar_range_atr (d=+0.30)
7. m15_move_atr (d=+0.27)
8. dist_5_ext_atr (d=-0.24)
9. reaction_score (d=-0.23)
10. bars_since_swing (d=+0.22)

LW-063194 (#9) ARCHETYPE: CHOP (descriptive: extended SHORT at 10-bar extreme)
LW-063196 (#11) ARCHETYPE: CHOP (descriptive: less extended, NEUTRAL 15m)

KEY CAUSAL DIFFERENCES BETWEEN #9 AND #11:
1. #9 at 10-bar extreme (dist_10=0); #11 inside range
2. #9 move_10_atr 3.76 vs #11 1.08; #9 m15_move 8.49 vs 1.93
3. #9 BEARISH 15m vs #11 NEUTRAL 15m

DOES ENTRY EXTENSION APPEAR RELATED TO FAILURE?
WEAK / INCONSISTENT (deciles non-monotonic last week; historical sign agrees)

DOES OPPORTUNITY AGE APPEAR RELATED TO FAILURE?
NO (all entries age=1 bar last week; no variance)

IS THERE A CLEAR SINGLE ENTRY-TIME FEATURE THAT REMOVES MANY LOSERS
WHILE RETAINING MOST WINNERS?
NO

HISTORICAL RELATIONSHIP AGREES WITH LAST WEEK:
MIXED (extension metrics yes; several secondary features flip)

SHOULD WE PROCEED TO A FILTER-VALIDATION PHASE?
NO — insufficient stable separation on 126-trade sample; extension signal weak/inconsistent

NO STRATEGY LOGIC CHANGED
NO PARAMETERS CHANGED
NO FILTER PROMOTED
DIAGNOSTIC ONLY
```
