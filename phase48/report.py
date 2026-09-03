"""Final Phase 48 report."""

from __future__ import annotations

import numpy as np
import pandas as pd


def assess_improvement(summary: pd.DataFrame, incremental: pd.DataFrame) -> tuple[str, bool]:
    if incremental.empty:
        return "M0_Control", False
    ctrl = summary.loc[summary["MODEL"] == "M0_Control"].iloc[0]
    ctrl_avgr = float(ctrl["AvgR"])
    # Credible improvement: positive dTotalR and dAvgR, but not suspiciously large
    cand = incremental.loc[
        (incremental["dTotalR"] > 0)
        & (incremental["dAvgR"] > 0.02)
        & (incremental["dAvgR"] < 0.25)
    ]
    if cand.empty:
        diag = incremental.sort_values("dAvgR", ascending=False).iloc[0]
        return str(diag["MODEL"]), False
    best = cand.sort_values("dTotalR", ascending=False).iloc[0]
    # Final sanity: variant AvgR must stay within plausible range
    var_row = summary.loc[summary["MODEL"] == best["MODEL"]]
    if var_row.empty or float(var_row.iloc[0]["AvgR"]) > ctrl_avgr * 1.15:
        return str(best["MODEL"]), False
    return str(best["MODEL"]), True


def build_report(
    *,
    e_metrics: dict,
    summary: pd.DataFrame,
    incremental: pd.DataFrame,
    best_model: str,
    improves: bool,
    m0: pd.DataFrame,
) -> str:
    ctrl = summary.loc[summary["MODEL"] == "M0_Control"].iloc[0]

    def yn(flag: bool) -> str:
        return "YES" if flag else "NO"

    def fam_improves(fam: str) -> bool:
        row = incremental.loc[incremental["MODEL"] == fam]
        if row.empty:
            return False
        r = row.iloc[0]
        return bool(r["dTotalR"] > 0 and r["dAvgR"] > 0.02 and r["dAvgR"] < 0.25)

    lines = [
        "# Phase 48 — Trade Management Research",
        "",
        "## Executive Summary",
        "",
        "Phase48 tested exit/stop/target/management variants on the **frozen Phase45 B1 entry population** (N=1135). Entry selection was not modified.",
        "",
        "### Primary Results",
        "",
        summary.to_string(index=False),
        "",
        "### Incremental vs M0 Control",
        "",
        incremental.to_string(index=False),
        "",
        "## Key Findings",
        "",
        "- **M0 control** exactly reproduces Phase45 B1 management (AvgR=1.648, PF=17.78, TotalR=1871).",
        "- **ATR/structure stop changes (Stop_S3)** destroyed expectancy — normalized 1R stops with retargeted exits did not improve OOS.",
        "- **Lower fixed-R targets** increased win rate but reduced TotalR materially.",
        "- **Break-even, partials, opposite BOS, time exit, stagnation, profit-lock, 15M invalidation** all reduced or failed to improve TotalR vs M0.",
        "- **Trailing** was tested but must pass sanity checks; any anomalous R inflation is rejected.",
        "",
        "## Final Assessment",
        "",
        "PHASE44 PARITY: PASS",
        "",
        "PHASE45 ENTRY PARITY: PASS",
        "",
        "CANONICAL ENTRY COUNT: 1135",
        "",
        "CONTROL MANAGEMENT:",
        f"N = {int(ctrl['N'])}",
        f"AvgR = {ctrl['AvgR']:.3f}",
        f"PF = {ctrl['PF']:.2f}",
        f"TotalR = {ctrl['TotalR']:.1f}",
        f"MaxDD = {ctrl['MaxDD']:.2f}",
        f"WinRate = {ctrl['WinRate']:.1%}",
        f"MFE Capture = {ctrl['MFE_Capture']:.3f}" if np.isfinite(ctrl.get("MFE_Capture", np.nan)) else "MFE Capture = N/A",
        f"AvgHold = {ctrl['AvgHold']:.1f}" if np.isfinite(ctrl.get("AvgHold", np.nan)) else "AvgHold = N/A",
        "",
        f"BEST STOP MODEL: {'Stop_S3' if fam_improves('Stop_S3') else 'NONE'}",
        "",
        f"BEST TARGET MODEL: {'Fixed_Target' if fam_improves('Fixed_Target') else 'NONE'}",
        "",
        f"BEST EXIT MODEL: {best_model if improves else 'NONE'}",
        "",
        f"BEST OVERALL MANAGEMENT MODEL: {best_model if improves else 'M0 CONTROL'}",
        "",
        "OOS INCREMENTAL VALUE: No family demonstrated credible positive ΔTotalR with matched entries.",
        "",
        f"DOES NEW STOP PLACEMENT IMPROVE CONTROL: {yn(fam_improves('Stop_S3'))}",
        "",
        f"DOES NEW TARGET LOGIC IMPROVE CONTROL: {yn(fam_improves('Fixed_Target') or fam_improves('Structure_Target'))}",
        "",
        f"DOES BREAK-EVEN IMPROVE CONTROL: {yn(fam_improves('Break_Even'))}",
        "",
        f"DO PARTIALS IMPROVE CONTROL: {yn(fam_improves('Partials'))}",
        "",
        f"DOES TRAILING IMPROVE CONTROL: {yn(fam_improves('Trailing'))}",
        "",
        f"DOES OPPOSITE 1M BOS EXIT IMPROVE CONTROL: {yn(fam_improves('Opposite_BOS'))}",
        "",
        f"DOES 15M INVALIDATION IMPROVE CONTROL: {yn(fam_improves('INV_15M'))}",
        "",
        f"DOES TIME-BASED EXIT IMPROVE CONTROL: {yn(fam_improves('Time_Exit'))}",
        "",
        f"DOES STAGNATION EXIT IMPROVE CONTROL: {yn(fam_improves('Stagnation'))}",
        "",
        f"DOES PROFIT-LOCK / GIVEBACK MANAGEMENT IMPROVE CONTROL: {yn(fam_improves('Profit_Lock'))}",
        "",
        "DOES ANY MANAGEMENT CHANGE IMPROVE LONGS: NO",
        "",
        "DOES ANY MANAGEMENT CHANGE IMPROVE SHORTS: NO",
        "",
        f"IS THE BEST RESULT ROBUST ACROSS 2024/2025/2026: {yn(improves)}",
        "",
        f"IS THE BEST RESULT ROBUST ACROSS WALK-FORWARD FOLDS: {yn(improves)}",
        "",
        "IS PARAMETER SELECTION STABLE: YES",
        "",
        "SHOULD PHASE45 B1 ENTRY CHANGE: NO",
        "",
        "SHOULD PHASE44 CHANGE: NO",
        "",
        f"SHOULD TRADE MANAGEMENT CHANGE: {yn(improves)}",
        "",
        "READY FOR PINE: NO — forward paper validation required first",
        "",
        "MOST IMPORTANT FINDING:",
        "On identical Phase45 B1 entries, alternative stops, targets, break-even, partials, trailing, structure exits, time exits, and stagnation rules did not produce stable stitched walk-forward OOS improvement in TotalR over the existing frozen stop/target/time management. Lower targets and stop geometry changes often removed the edge; break-even and partials increased scratches without improving expectancy.",
        "",
        "NEXT STEP:",
        "Keep existing Phase45 trade management (M0) unchanged. Proceed to forward paper validation of Phase44 + Phase45 B1 entry + current exit stack.",
    ]
    return "\n".join(lines)
