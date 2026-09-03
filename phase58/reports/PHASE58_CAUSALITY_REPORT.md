# Phase58 Causality Report

## Architecture
- Sequential bar-close processing via TraderEngine.on_bar_close(i)
- Context: precomputed causal swing arrays + completed HTF bars only
- Location: running pullback extreme (no future deepest_i)
- Reaction: 6 evidence components using only bar i and past bars
- Entry: next-bar open after signal (i+1)

## No Future Data
- No deepest_i, no future Leg2, no backward fill
- Swing confirmation: j = i - swing lag
- HTF alignment: Phase55 convention (last completed bar)
- Move capture / directional accuracy: LABELS ONLY, never features

## PHASE58 CAUSALITY: PASS
