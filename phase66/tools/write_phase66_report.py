#!/usr/bin/env python3
"""Regenerate Phase66 report from phase66_audit.json."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "phase66" / "reports" / "phase66_audit.json"
OUT_PATH = ROOT / "phase66" / "reports" / "PHASE66_CAUSAL_PRICE_ACTION_ENTRY_AUDIT.md"
GATE_PO2 = 0.38


def _pct(v):
    return f"{v:.1%}" if v is not None else "N/A"


def _fmt_family_block(fam: str, f: dict) -> list[str]:
    p, s, g = f["path"], f["sim_net"], f["sim_gross"]
    stress = f.get("stress_1.5x", {})
    gross_r = g.get("AvgR", 0)
    cost_r = s.get("avg_cost_R", 0)
    stress2 = gross_r - 2 * cost_r
    return [
        f"--------------------------------------------",
        f"{fam} — {'FAILED PUSH / REJECTION' if fam == 'E1' else 'BREAK + ACCEPTANCE' if fam == 'E2' else 'FAILED BREAK + RECLAIM'}",
        f"--------------------------------------------",
        "",
        "Definition:",
        "  E1: probe beyond 5-bar micro extreme, close back inside → fade",
        "  E2: close breaks 5-bar level with open inside → continuation",
        "  E3: break beyond 5-bar level, close reclaims, open on prior side → fade",
        "Causal level: prior 5-bar high/low (excludes current bar)",
        "Entry: next bar open after trigger bar close (timing B)",
        "",
        f"N: {f['n_signals']:,}",
        f"LONG: {f['n_long']:,}",
        f"SHORT: {f['n_short']:,}",
        f"Retention: {f['retention']:.1%}",
        f"Expired (no event T0–T+3): {f['n_expired']:,}",
        f"Conflicts: {f['n_conflict']:,}",
        "",
        f"Median delay: {f['median_delay']:.1f} bars",
        f"Median chase: {f['median_chase']:.2f} ATR",
        "",
        f"MFE 3m: {p.get('median_mfe_3m', 0):.2f} ATR",
        f"MAE 3m: {p.get('median_mae_3m', 0):.2f} ATR",
        f"MFE 5m: {p.get('median_mfe_5m', 0):.2f} ATR",
        f"MAE 5m: {p.get('median_mae_5m', 0):.2f} ATR",
        f"MFE 15m: {p.get('median_mfe_15m', 0):.2f} ATR",
        f"MAE 15m: {p.get('median_mae_15m', 0):.2f} ATR",
        f"MFE 60m: {p.get('median_mfe_60m', 0):.2f} ATR",
        f"MAE 60m: {p.get('median_mae_60m', 0):.2f} ATR",
        "",
        f"+1 before -1: {_pct(p.get('+1_before_-1'))}",
        f"+1.5 before -1: {_pct(p.get('+1.5_before_-1'))}",
        f"+2 before -1: {_pct(p.get('+2_before_-1'))}",
        f"+2.5 before -1: {_pct(p.get('+2.5_before_-1'))}",
        f"+1 before -1.5: {_pct(p.get('+1_before_-1.5'))}",
        f"+2 before -1.5: {_pct(p.get('+2_before_-1.5'))}",
        f"+2.5 before -1.5: {_pct(p.get('+2.5_before_-1.5'))}",
        "",
        f"Natural stop (median): {s.get('median_risk_atr', 0):.2f} ATR",
        f"Gross AvgR: {gross_r:.4f}",
        f"Cost R (avg): {cost_r:.4f}",
        f"Net AvgR: {s.get('AvgR', 0):.4f}",
        f"PF net: {s.get('PF', 0):.3f}",
        f"Net TotalR: {s.get('TotalR', 0):.0f}",
        f"MaxDD: {s.get('MaxDD', 0):.0f}",
        f"1.5x cost Net AvgR: {stress.get('AvgR', 0):.4f}",
        f"2x cost Net AvgR (est): {stress2:.4f}",
        "",
        f"VERDICT: {f.get('verdict', 'REJECT')}",
        "",
    ]


def main():
    r = json.loads(JSON_PATH.read_text())
    bl = r["baselines"]["original"]
    m65 = r["baselines"]["m65"]
    best = r["best_family"]
    bf = r["families"][best]
    po2_best = bf["path"].get("+2_before_-1", 0)
    net_pos = bf["sim_net"].get("AvgR", 0) > 0
    pos_years = sum(1 for y, v in r.get("years", {}).items() if v.get("AvgR", -999) > 0)
    total_years = len(r.get("years", {}))

    lines = [
        "CAUSAL PRICE-ACTION ENTRY DISCOVERY AT PHASE58 LOCATIONS",
        "=======================================================",
        "",
        f"CAUSALITY: {'PASS' if r['causality']['sequential_parity'] else 'FAIL'}",
        f"PREFIX INVARIANCE: {'PASS' if r['causality']['prefix_invariance'] else 'FAIL'}",
        "FUTURE LEAKAGE: NONE",
        "PHASE58 LOCATION ENGINE MODIFIED: NO",
        "PHASE58 DIRECTION USED: NO (stored for diagnostics only)",
        "",
        "--------------------------------------------",
        "POPULATION",
        "--------------------------------------------",
        "",
        f"PHASE58 LOCATIONS: {r['n_alarms']:,}",
        f"LOCATIONS WITH E1: {r['counts']['E1']:,} ({r['counts']['E1']/r['n_alarms']:.1%})",
        f"LOCATIONS WITH E2: {r['counts']['E2']:,} ({r['counts']['E2']/r['n_alarms']:.1%})",
        f"LOCATIONS WITH E3: {r['counts']['E3']:,} ({r['counts']['E3']/r['n_alarms']:.1%})",
        f"NO PRICE-ACTION EVENT (any family, T0–T+3): {r['four_way']['phase58_no_pa']:,}",
        f"CONFLICTING EVENTS: E1={r['counts']['conflict']['E1']:,} E2={r['counts']['conflict']['E2']:,} E3={r['counts']['conflict']['E3']:,}",
        "",
        "--------------------------------------------",
        "BASELINES",
        "--------------------------------------------",
        "",
        "PHASE58 ORIGINAL DIRECTION (T+1 open, 1 ATR stop, 2.5R target):",
        f"  N: {bl['path']['n']:,}",
        f"  +1/-1: {_pct(bl['path'].get('+1_before_-1'))}",
        f"  +2/-1: {_pct(bl['path'].get('+2_before_-1'))}",
        f"  MFE 15m: {bl['path'].get('median_mfe_15m', 0):.2f} ATR",
        f"  MAE 15m: {bl['path'].get('median_mae_15m', 0):.2f} ATR",
        f"  Net AvgR: {bl['sim'].get('AvgR', 0):.4f}",
        "",
        "PHASE65 MARKET CHOICE (M3):",
        f"  N: {m65.get('n', m65['path']['n']):,}",
        f"  +1/-1: {_pct(m65['path'].get('+1_before_-1'))}",
        f"  +2/-1: {_pct(m65['path'].get('+2_before_-1'))}",
        f"  Net AvgR: {m65['sim'].get('AvgR', 0):.4f}",
        "",
    ]

    for fam in ["E1", "E2", "E3"]:
        lines.extend(_fmt_family_block(fam, r["families"][fam]))

    pa = r["pa_only"]
    lines.extend([
        "--------------------------------------------",
        "PRICE ACTION WITHOUT PHASE58 (matched controls, n≈10k sample)",
        "--------------------------------------------",
        "",
    ])
    for fam in ["E1", "E2", "E3"]:
        p58 = r["families"][fam]
        po = pa[fam]
        lift = p58["path"].get("+2_before_-1", 0) - po["path"].get("+2_before_-1", 0)
        lines.extend([
            f"{fam} ONLY (no Phase58):",
            f"  N: {po['n']:,}",
            f"  +2/-1: {_pct(po['path'].get('+2_before_-1'))}",
            f"  Net AvgR: {po['sim'].get('AvgR', 0):.4f}",
            f"{fam} + PHASE58:",
            f"  N: {p58['n_signals']:,}",
            f"  +2/-1: {_pct(p58['path'].get('+2_before_-1'))}",
            f"  Net AvgR: {p58['sim_net'].get('AvgR', 0):.4f}",
            f"  Phase58 path lift (+2/-1): {lift:+.1%}",
            "",
        ])

    ag = r["agreement"]
    lines.extend([
        "--------------------------------------------",
        "DIRECTION AGREEMENT (best family E2)",
        "--------------------------------------------",
        "",
        "PRICE ACTION AGREES WITH PHASE58:",
        f"  N: {ag['agree']['path']['n']:,}",
        f"  +2/-1: {_pct(ag['agree']['path'].get('+2_before_-1'))}",
        f"  Net AvgR: {ag['agree']['sim'].get('AvgR', 0):.4f}",
        "",
        "PRICE ACTION DISAGREES WITH PHASE58:",
        f"  N: {ag['disagree']['path']['n']:,}",
        f"  +2/-1: {_pct(ag['disagree']['path'].get('+2_before_-1'))}",
        f"  Net AvgR: {ag['disagree']['sim'].get('AvgR', 0):.4f}",
        "",
        "PHASE58 DIRECTION ADDS VALUE: NO (path and net nearly identical)",
        "",
        "--------------------------------------------",
        "WALK-FORWARD (E2, chronological 60/20/20)",
        "--------------------------------------------",
        "",
    ])
    for split in ["train", "validation", "holdout"]:
        w = r["walkforward"][split]
        lines.extend([
            f"{split.upper()}:",
            f"  N: {w['N']:,}",
            f"  +2/-1: (not stored per split)",
            f"  Net AvgR: {w['AvgR']:.4f}",
            f"  PF: {w['PF']:.3f}",
            f"  TotalR: {w['TotalR']:.0f}",
            "",
        ])

    lines.extend([
        "--------------------------------------------",
        "YEAR STABILITY (E2)",
        "--------------------------------------------",
        "",
    ])
    for y in sorted(r["years"]):
        v = r["years"][str(y) if str(y) in r["years"] else y]
        lines.append(
            f"  {y}: N={v['N']:,} Net AvgR={v['AvgR']:.3f} PF={v['PF']:.2f} TotalR={v['TotalR']:.0f}"
        )
    lines.extend([
        "",
        f"POSITIVE NET YEARS: {pos_years}/{total_years}",
        "",
        "--------------------------------------------",
        "ROBUSTNESS",
        "--------------------------------------------",
        "",
        f"PARAMETER CLIFF: NO (single broad definition per family, no grid search)",
        f"COST STRESS: FAIL (all families net negative at 1x, 1.5x, 2x)",
        f"OVERLAP INFLATION: not computed (independent-trade metrics reported)",
        f"ENTRY DELAY: MEDIUM (median 2 bars after alarm)",
        f"CHASE: MEDIUM–HIGH (E2 median 0.99 ATR; E1/E3 ~0.59 ATR)",
        "",
        "--------------------------------------------",
        "BEST ENTRY FAMILY",
        "--------------------------------------------",
        "",
        f"NAME: {best}",
        "LOCATION: Phase58 causal alarm (frozen 87,798)",
        "CAUSAL LEVEL: prior 5-bar high/low",
        "TRIGGER: close breaks/ rejects 5-bar level on trigger bar",
        "DIRECTION: price-action defined (LONG/SHORT from event)",
        "ENTRY: next bar open (T+1 from trigger)",
        "INVALIDATION: beyond failed extreme (E1/E3) or accepted level (E2)",
        f"MEDIAN DELAY: {bf['median_delay']:.1f} bars",
        f"MEDIAN CHASE: {bf['median_chase']:.2f} ATR",
        f"MEDIAN STOP ATR: {bf['sim_net'].get('median_risk_atr', 0):.2f}",
        f"+1 BEFORE -1: {_pct(bf['path'].get('+1_before_-1'))}",
        f"+2 BEFORE -1: {_pct(bf['path'].get('+2_before_-1'))}",
        f"+2 BEFORE -1.5: {_pct(bf['path'].get('+2_before_-1.5'))}",
        f"GROSS AVGR: {bf['sim_gross'].get('AvgR', 0):.4f}",
        f"COST R: {bf['sim_net'].get('avg_cost_R', 0):.4f}",
        f"NET AVGR: {bf['sim_net'].get('AvgR', 0):.4f}",
        f"PF: {bf['sim_net'].get('PF', 0):.3f}",
        f"NET TOTALR: {bf['sim_net'].get('TotalR', 0):.0f}",
        f"MAXDD: {bf['sim_net'].get('MaxDD', 0):.0f}",
        f"HOLDOUT Net AvgR: {r['walkforward']['holdout']['AvgR']:.4f}",
        "",
        "--------------------------------------------",
        "PHASE58 VALUE",
        "--------------------------------------------",
        "",
        "PRICE ACTION WORKS WITHOUT PHASE58: NO (E2 +2/-1 20.7% vs 34.1% at Phase58)",
        "PHASE58 IMPROVES PRICE ACTION: LARGE (path ordering)",
        "PHASE58 IMPROVES ECONOMICS: NO (both strongly net negative)",
        "PHASE58 SHOULD REMAIN IN ARCHITECTURE: CONTEXT ONLY (location alarm, not entry filter)",
        "",
        "--------------------------------------------",
        "CENTRAL ANSWER",
        "--------------------------------------------",
        "",
        f"FAILED PUSH HAS DIRECTIONAL EDGE: {'MARGINAL PATH ONLY' if r['families']['E1']['path'].get('+2_before_-1',0) > 0.33 else 'NO'} (+2/-1 {_pct(r['families']['E1']['path'].get('+2_before_-1'))}, net negative)",
        f"BREAK + ACCEPTANCE HAS DIRECTIONAL EDGE: {'MARGINAL PATH ONLY' if po2_best > 0.33 else 'NO'} (+2/-1 {_pct(po2_best)}, best path family)",
        f"FAILED BREAK + RECLAIM HAS DIRECTIONAL EDGE: {'MARGINAL PATH ONLY' if r['families']['E3']['path'].get('+2_before_-1',0) > 0.33 else 'NO'} (+2/-1 {_pct(r['families']['E3']['path'].get('+2_before_-1'))})",
        f"ANY SIMPLE PRICE-ACTION ENTRY HAS REAL EDGE: {'NO' if po2_best < GATE_PO2 else 'YES'}",
        f"EDGE SURVIVES COSTS: NO",
        f"EDGE SURVIVES HOLDOUT: NO",
        "",
        "--------------------------------------------",
        "VERDICT",
        "--------------------------------------------",
        "",
        "NEW CAUSAL ENTRY EDGE FOUND: NO",
        "ENTRY IS EARLY ENOUGH: YES (median 2 bars, T+3 window enforced)",
        "DIRECTIONAL ASYMMETRY MEANINGFUL: NO (+1/-1 ~50% at best; MFE≈MAE)",
        "NET EXPECTANCY POSITIVE: NO",
        "ROBUST: NO (0 positive net years on E2)",
        "OVER-OPTIMIZED: NO (single broad rule per family)",
        "READY TO FREEZE: NO",
        "READY FOR MANUAL VISUAL VALIDATION: NO (no candidate to validate)",
        "READY FOR PINE: NO",
        "READY FOR LIVE: NO",
        "",
        "NEXT RESEARCH REQUIRED:",
        "  STOP this branch. Simple causal E1/E2/E3 at Phase58 locations do not produce",
        "  tradeable directional edge after costs. Phase58 remains a valid LOCATION alarm",
        "  (Phase64) but entry must come from elsewhere — test price-action independently",
        "  of Phase58, or begin a genuinely new edge-discovery branch. Do NOT combine",
        "  weak families or optimize management to rescue negative expectancy.",
        "",
    ])
    OUT_PATH.write_text("\n".join(lines))
    print(OUT_PATH)


if __name__ == "__main__":
    main()
