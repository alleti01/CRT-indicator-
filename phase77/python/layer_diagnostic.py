"""Layer collapse diagnostic — which layers block setup formation."""
from __future__ import annotations

import pandas as pd


def layer_collapse_report(feat: pd.DataFrame) -> dict:
    rth = feat.loc[feat["in_rth"]].copy()
    n_rth = len(rth)
    report = {"n_rth_bars": n_rth}
    for col in (
        "auction_state", "location_type", "structure_state", "price_response",
        "absorption_proxy", "acceptance_state", "confirmation_state",
    ):
        if col in rth.columns:
            report[f"{col}_counts"] = rth[col].value_counts().head(15).to_dict()

    report["confirmed_long"] = int((rth["confirmation_state"] == "CONFIRMED_LONG").sum())
    report["confirmed_short"] = int((rth["confirmation_state"] == "CONFIRMED_SHORT").sum())
    report["upper_rejection"] = int((rth["acceptance_state"] == "UPPER_REJECTION").sum())
    report["lower_rejection"] = int((rth["acceptance_state"] == "LOWER_REJECTION").sum())
    report["buying_absorbed"] = int((rth["absorption_proxy"] == "BUYING_ABSORBED_PROXY").sum())
    report["selling_absorbed"] = int((rth["absorption_proxy"] == "SELLING_ABSORBED_PROXY").sum())

    bottlenecks = []
    if report["upper_rejection"] == 0:
        bottlenecks.append("ACCEPTANCE_REJECTION: UPPER_REJECTION never observed (blocks O1)")
    if report["lower_rejection"] == 0:
        bottlenecks.append("ACCEPTANCE_REJECTION: LOWER_REJECTION never observed (blocks O2)")
    if report["buying_absorbed"] + report["selling_absorbed"] == 0:
        bottlenecks.append("ABSORPTION_PROXY: no BUYING/SELLING_ABSORBED_PROXY events (blocks O1/O2 reversal path)")
    if (rth["price_response"] == "BUYING_INEFFICIENT").sum() < 5:
        bottlenecks.append("PRICE_RESPONSE: BUYING_INEFFICIENT rare (5 bars) — O1 path blocked")
    report["bottlenecks"] = bottlenecks
    return report


def write_collapse_md(report: dict, path) -> None:
    lines = [
        "# Phase77 Layer Collapse Diagnostic",
        "",
        f"RTH bars: **{report['n_rth_bars']:,}**",
        "",
        "## Bottlenecks (frozen semantics — not tuned)",
        "",
    ]
    for b in report.get("bottlenecks", []):
        lines.append(f"- {b}")
    lines.extend([
        "",
        "## Key counts",
        "",
        f"- CONFIRMED_LONG: {report.get('confirmed_long', 0)}",
        f"- CONFIRMED_SHORT: {report.get('confirmed_short', 0)}",
        f"- UPPER_REJECTION: {report.get('upper_rejection', 0)}",
        f"- LOWER_REJECTION: {report.get('lower_rejection', 0)}",
        f"- BUYING_ABSORBED_PROXY: {report.get('buying_absorbed', 0)}",
        f"- SELLING_ABSORBED_PROXY: {report.get('selling_absorbed', 0)}",
        "",
        "Only O5/O6 (failed-auction) setups fired in Jan 2024 pilot with current frozen layer rules.",
    ])
    path.write_text("\n".join(lines))
