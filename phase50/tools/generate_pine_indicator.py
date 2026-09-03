#!/usr/bin/env python3
"""Generate Phase50 MTF Pine indicator from Phase44 template + B1/M0 layer."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P44 = ROOT / "phase44" / "results" / "quality_filtered_pine" / "NQ15_PHASE44_QUALITY_INDICATOR.pine"
OUT = ROOT / "phase50" / "pine" / "phase50_nq_indicator.pine"
FOOTER = Path(__file__).with_name("_phase50_footer.pine")

HEADER = """//@version=6
// Phase 50 — NQ 1M execution + 15M Phase44 context + B1 Micro-BOS + M0
// Python: phase44/, phase45/execution/confirm.py, phase45/execution/simulate.py

indicator(
     "Phase50 NQ Phase44 + B1 + M0",
     shorttitle = "P50_NQ",
     overlay = true,
     max_labels_count = 500,
     max_lines_count = 500,
     max_boxes_count = 100)

bool chart1m = timeframe.period == "1"
"""


def _indent(lines: list[str], n: int = 4) -> list[str]:
    pad = " " * n
    return [pad + ln if ln.strip() else "" for ln in lines]


def _patch(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        out.append(ln)
        if "p31FillEvt := true" in ln:
            out += [
                "                        p44OutFill := true",
                "                        p44OutDir := p31Dir",
                "                        p44OutSetup := p31Dir == 1 ? 1 : 2",
                '                        p44OutTier := p31ConfTier == "A+" ? 1 : p31ConfTier == "A" ? 2 : 3',
                "                        p44OutEntry := p31Entry",
                "                        p44OutStop := p31Stop",
                "                        p44OutTarget := p31Target",
                "                        p44OutScore := lastQualityScore",
            ]
        if "rvFillLongEvt := true" in ln:
            out += [
                "                        p44OutFill := true",
                "                        p44OutDir := 1",
                "                        p44OutSetup := 3",
                '                        p44OutTier := rvConfTier == "A+" ? 1 : rvConfTier == "A" ? 2 : 3',
                "                        p44OutEntry := rvFillEntry",
                "                        p44OutStop := st",
                "                        p44OutTarget := tg",
                "                        p44OutScore := lastQualityScore",
            ]
        if "rvFillShortEvt := true" in ln:
            out += [
                "                        p44OutFill := true",
                "                        p44OutDir := -1",
                "                        p44OutSetup := 4",
                '                        p44OutTier := rvConfTier == "A+" ? 1 : rvConfTier == "A" ? 2 : 3',
                "                        p44OutEntry := rvFillEntry",
                "                        p44OutStop := st",
                "                        p44OutTarget := tg",
                "                        p44OutScore := lastQualityScore",
            ]
    return out


def main() -> None:
    src = P44.read_text().splitlines()
    constants = src[14:72]  # FROZEN CONSTANTS + types
    helpers = src[87:173]   # inRth .. tradeLevelsOk
    loop = _patch(src[205:608])
    loop = [ln.replace("and tfOk", "").replace("tfOk and ", "") for ln in loop if "timeframe.period" not in ln]

    bundle = [
        "phase44ExportBundle() =>",
        "    bool p44OutFill = false",
        "    float p44OutDir = 0",
        "    float p44OutSetup = 0",
        "    float p44OutTier = 0",
        "    float p44OutEntry = na",
        "    float p44OutStop = na",
        "    float p44OutTarget = na",
        "    float p44OutScore = na",
        *_indent(loop),
        "    [p44OutFill ? 1.0 : 0.0, p44OutDir, p44OutSetup, p44OutTier, p44OutEntry, p44OutStop, p44OutTarget, float(time), p44OutScore]",
        "",
    ]

    footer = FOOTER.read_text()

    text = HEADER + "\n".join(constants) + "\n\n" + "\n".join(helpers) + "\n\n" + "\n".join(bundle) + footer
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(f"Wrote {OUT} ({len(text.splitlines())} lines)")


if __name__ == "__main__":
    main()
