"""Patch Phase 40 Pine into Phase 44 quality-filtered Pine."""

from __future__ import annotations

from pathlib import Path

from .config import Q_PASS_MIN, Q_RAW_HI, Q_RAW_LO, Q_TIER_A, Q_TIER_APLUS, Q_TIER_B


def patch_indicator(src: str) -> str:
    text = src
    text = text.replace(
        "// NQ 15m Combined — Phase 40 Impulse Filter (Phase 31 + Phase 33 Concurrent)",
        "// NQ 15m Combined — Phase 44 Quality Filter (Phase 40 + Phase 43 simple score)",
    )
    text = text.replace(
        '     "NQ 15M Combined Phase 40 Impulse Filter"',
        '     "NQ 15M Combined Phase 44 Quality Filter"',
    )
    text = text.replace('     shorttitle = "NQ15_P40"', '     shorttitle = "NQ15_P44"')

    text = text.replace(
        "const float FZ_IMPULSE_MIN     = 0.65",
        f"""const float FZ_IMPULSE_MIN     = 0.65
const float FZ_Q_RAW_LO          = {Q_RAW_LO}
const float FZ_Q_RAW_HI          = {Q_RAW_HI}
const float FZ_Q_PASS_MIN        = {Q_PASS_MIN}
const float FZ_Q_TIER_APLUS      = {Q_TIER_APLUS}
const float FZ_Q_TIER_A          = {Q_TIER_A}
const float FZ_Q_TIER_B          = {Q_TIER_B}""",
    )

    text = text.replace(
        "bool impulsePass = not na(impulse3Bar()) and impulse3Bar() >= FZ_IMPULSE_MIN",
        """bool impulsePass = not na(impulse3Bar()) and impulse3Bar() >= FZ_IMPULSE_MIN

qualityRaw(int dir) =>
    float r1 = close[1] != 0 ? ((close - close[1]) / close[1]) * dir : 0.0
    float r2 = close[2] != 0 ? ((close - close[2]) / close[2]) * dir : 0.0
    float r3 = close[3] != 0 ? ((close - close[3]) / close[3]) * dir : 0.0
    r1 + r2 + r3

qualityScore(int dir) =>
    float raw = qualityRaw(dir)
    float span = FZ_Q_RAW_HI - FZ_Q_RAW_LO
    span > 0 ? math.max(0.0, math.min(100.0, (raw - FZ_Q_RAW_LO) / span * 100.0)) : 50.0

qualityPass(int dir) =>
    qualityScore(dir) >= FZ_Q_PASS_MIN

confidenceTier(int dir) =>
    float s = qualityScore(dir)
    s >= FZ_Q_TIER_APLUS ? "A+" : s >= FZ_Q_TIER_A ? "A" : s >= FZ_Q_TIER_B ? "B" : "C\"""",
    )

    text = text.replace(
        'bool showRejected = input.bool(false, "Show Rejected Signals", group = GRP)',
        'bool showRejected = input.bool(false, "Show Impulse Rejected", group = GRP)\n'
        'bool showQualityRejected = input.bool(false, "Show Quality Rejected", group = GRP)\n'
        'bool showConfidence = input.bool(true, "Show Confidence Tier", group = GRP)',
    )

    text = text.replace(
        "var bool p31RejectEvt = false\nvar int  p31RejectDir = 0",
        "var bool p31RejectEvt = false\nvar bool p31QualRejectEvt = false\nvar int  p31RejectDir = 0\nvar int  p31QualRejectDir = 0\nvar string p31ConfTier = \"\"\nfloat lastQualityScore = na",
    )
    text = text.replace(
        "var bool rvRejectLongEvt = false\nvar bool rvRejectShortEvt = false",
        "var bool rvRejectLongEvt = false\nvar bool rvRejectShortEvt = false\nvar bool rvQualRejectLongEvt = false\nvar bool rvQualRejectShortEvt = false\nvar string rvConfTier = \"\"",
    )

    text = text.replace(
        "    p31RejectEvt := false\n    p31RejectDir := 0",
        "    p31RejectEvt := false\n    p31QualRejectEvt := false\n    p31RejectDir := 0\n    p31QualRejectDir := 0\n    p31ConfTier := \"\"\n    rvQualRejectLongEvt := false\n    rvQualRejectShortEvt := false\n    rvConfTier := \"\"",
    )

    # Continuation entry gate
    text = text.replace(
        """                if impulsePass
                    p31Entry := px
                    float risk = FZ_P31_STOP_ATR * atrVal
                    p31Stop := p31Dir == 1 ? p31Entry - risk : p31Entry + risk
                    p31Target := p31Dir == 1 ? p31Entry + FZ_P31_TARGET_R * risk : p31Entry - FZ_P31_TARGET_R * risk
                    p31Held := 0
                    p31State := ST_ACTIVE
                    p31EntryBar := bar_index
                    p31FillEvt := true
                    p31FillDir := p31Dir
                    if showLevels and tradeLevelsOk(p31Entry, p31Stop, p31Target)
                        deleteLine(p31LnE)
                        deleteLine(p31LnS)
                        deleteLine(p31LnT)
                        p31LnE := newLevelLine(p31EntryBar, p31Entry, bar_index, p31Entry, color.blue, 20)
                        p31LnS := newLevelLine(p31EntryBar, p31Stop, bar_index, p31Stop, color.red, 20)
                        p31LnT := newLevelLine(p31EntryBar, p31Target, bar_index, p31Target, color.lime, 20)
                else
                    p31RejectEvt := true
                    p31RejectDir := p31Dir
                    p31State := ST_IDLE
                    p31Dir := 0""",
        """                if impulsePass
                    if qualityPass(p31Dir)
                        p31Entry := px
                        float risk = FZ_P31_STOP_ATR * atrVal
                        p31Stop := p31Dir == 1 ? p31Entry - risk : p31Entry + risk
                        p31Target := p31Dir == 1 ? p31Entry + FZ_P31_TARGET_R * risk : p31Entry - FZ_P31_TARGET_R * risk
                        p31Held := 0
                        p31State := ST_ACTIVE
                        p31EntryBar := bar_index
                        p31FillEvt := true
                        p31FillDir := p31Dir
                        lastQualityScore := qualityScore(p31Dir)
                        p31ConfTier := confidenceTier(p31Dir)
                        if showLevels and tradeLevelsOk(p31Entry, p31Stop, p31Target)
                            deleteLine(p31LnE)
                            deleteLine(p31LnS)
                            deleteLine(p31LnT)
                            p31LnE := newLevelLine(p31EntryBar, p31Entry, bar_index, p31Entry, color.blue, 20)
                            p31LnS := newLevelLine(p31EntryBar, p31Stop, bar_index, p31Stop, color.red, 20)
                            p31LnT := newLevelLine(p31EntryBar, p31Target, bar_index, p31Target, color.lime, 20)
                    else
                        p31QualRejectEvt := true
                        p31QualRejectDir := p31Dir
                        p31State := ST_IDLE
                        p31Dir := 0
                else
                    p31RejectEvt := true
                    p31RejectDir := p31Dir
                    p31State := ST_IDLE
                    p31Dir := 0""",
    )

    # Reversal entry gate
    text = text.replace(
        """            if impulsePass
                if rDir == 1
                    seenRl := true
                    rvFillLongEvt := true
                else
                    seenRs := true
                    rvFillShortEvt := true
                rvFillEntry := px
                array.push(rvOpen, RvOpenTrade.new(rDir, px, st, tg, 0, bar_index))
                if showLevels and tradeLevelsOk(px, st, tg)
                    deleteLine(rvLnE)
                    deleteLine(rvLnS)
                    deleteLine(rvLnT)
                    rvLnE := newLevelLine(bar_index, px, bar_index, px, color.teal, 30)
                    rvLnS := newLevelLine(bar_index, st, bar_index, st, color.red, 30)
                    rvLnT := newLevelLine(bar_index, tg, bar_index, tg, color.orange, 30)
            else
                if rDir == 1
                    rvRejectLongEvt := true
                else
                    rvRejectShortEvt := true""",
        """            if impulsePass
                if qualityPass(rDir)
                    if rDir == 1
                        seenRl := true
                        rvFillLongEvt := true
                    else
                        seenRs := true
                        rvFillShortEvt := true
                    rvFillEntry := px
                    lastQualityScore := qualityScore(rDir)
                    rvConfTier := confidenceTier(rDir)
                    array.push(rvOpen, RvOpenTrade.new(rDir, px, st, tg, 0, bar_index))
                    if showLevels and tradeLevelsOk(px, st, tg)
                        deleteLine(rvLnE)
                        deleteLine(rvLnS)
                        deleteLine(rvLnT)
                        rvLnE := newLevelLine(bar_index, px, bar_index, px, color.teal, 30)
                        rvLnS := newLevelLine(bar_index, st, bar_index, st, color.red, 30)
                        rvLnT := newLevelLine(bar_index, tg, bar_index, tg, color.orange, 30)
                else
                    if rDir == 1
                        rvQualRejectLongEvt := true
                    else
                        rvQualRejectShortEvt := true
            else
                if rDir == 1
                    rvRejectLongEvt := true
                else
                    rvRejectShortEvt := true""",
    )

    qual_rej_shapes = """
plotshape(showQualityRejected and barstate.isconfirmed and p31QualRejectEvt and p31QualRejectDir == 1, "Quality Rejected Long", shape.cross, location.belowbar, color.new(color.orange, 20), size = size.tiny, text = "C")
plotshape(showQualityRejected and barstate.isconfirmed and p31QualRejectEvt and p31QualRejectDir == -1, "Quality Rejected Short", shape.cross, location.abovebar, color.new(color.orange, 20), size = size.tiny, text = "C")
plotshape(showQualityRejected and barstate.isconfirmed and rvQualRejectLongEvt, "Quality Rejected RL", shape.cross, location.belowbar, color.new(color.orange, 30), size = size.tiny, text = "C")
plotshape(showQualityRejected and barstate.isconfirmed and rvQualRejectShortEvt, "Quality Rejected RS", shape.cross, location.abovebar, color.new(color.orange, 30), size = size.tiny, text = "C")
"""
    text = text.replace(
        'plotshape(showRejected and barstate.isconfirmed and p31RejectEvt and p31RejectDir == 1',
        qual_rej_shapes + '\nplotshape(showRejected and barstate.isconfirmed and p31RejectEvt and p31RejectDir == 1',
    )

    conf_labels = """
if showConfidence and barstate.isconfirmed
    if p31FillEvt
        label.new(bar_index, p31FillDir == 1 ? low : high, p31ConfTier, style = label.style_none, xloc = xloc.bar_index, yloc = yloc.price, textcolor = color.white, color = color.new(color.black, 100), size = size.tiny)
    if rvFillLongEvt or rvFillShortEvt
        label.new(bar_index, rvFillLongEvt ? low : high, rvConfTier, style = label.style_none, xloc = xloc.bar_index, yloc = yloc.price, textcolor = color.white, color = color.new(color.black, 100), size = size.tiny)
"""
    text = text.replace(
        "if showTfWarn and not tfOk and barstate.islast:",
        conf_labels + "\nvar table p44Panel = table.new(position.top_right, 2, 10, border_width = 1)\n"
        "if barstate.islast\n"
        "    table.cell(p44Panel, 0, 0, \"Arch\", text_color = color.white, bgcolor = color.new(color.black, 20))\n"
        "    table.cell(p44Panel, 1, 0, \"P44 Quality\", text_color = color.white, bgcolor = color.new(color.black, 20))\n"
        "    table.cell(p44Panel, 0, 1, \"TF\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 1, timeframe.period, text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 0, 2, \"Impulse\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 2, str.tostring(impulse3Bar(), \"#.###\"), text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 0, 3, \"Quality\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 3, na(lastQualityScore) ? \"—\" : str.tostring(lastQualityScore, \"#.0\"), text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 0, 4, \"Tier\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 4, p31FillEvt ? p31ConfTier : rvFillLongEvt or rvFillShortEvt ? rvConfTier : \"—\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 0, 5, \"Filter\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 5, impulsePass ? \"IMP OK\" : \"IMP FAIL\", text_color = impulsePass ? color.lime : color.red, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 0, 6, \"Entry\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 6, na(p31Entry) and na(rvFillEntry) ? \"—\" : str.tostring(na(p31Entry) ? rvFillEntry : p31Entry, \"#.##\"), text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 0, 7, \"Stop\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 7, na(p31Stop) ? \"—\" : str.tostring(p31Stop, \"#.##\"), text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 0, 8, \"Target\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 8, na(p31Target) ? \"—\" : str.tostring(p31Target, \"#.##\"), text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 0, 9, \"15m\", text_color = color.white, bgcolor = color.new(color.black, 30))\n"
        "    table.cell(p44Panel, 1, 9, tfOk ? \"OK\" : \"WRONG\", text_color = tfOk ? color.lime : color.red, bgcolor = color.new(color.black, 30))\n\n"
        "if showTfWarn and not tfOk and barstate.islast:",
    )

    # Strategy-specific entry gates (same quality layer)
    text = text.replace(
        """                if impulsePass
                    float risk = FZ_P31_STOP_ATR * atrVal
                    p31Stop := p31Dir == 1 ? px - risk : px + risk
                    p31Target := p31Dir == 1 ? px + FZ_P31_TARGET_R * risk : px - FZ_P31_TARGET_R * risk
                    p31Held := 0
                    p31State := ST_ACTIVE
                    if p31Dir == 1
                        strategy.entry("P31", strategy.long, comment = "L")
                    else
                        strategy.entry("P31", strategy.short, comment = "S")
                else
                    p31State := ST_IDLE
                    p31Dir := 0""",
        """                if impulsePass
                    if qualityPass(p31Dir)
                        float risk = FZ_P31_STOP_ATR * atrVal
                        p31Stop := p31Dir == 1 ? px - risk : px + risk
                        p31Target := p31Dir == 1 ? px + FZ_P31_TARGET_R * risk : px - FZ_P31_TARGET_R * risk
                        p31Held := 0
                        p31State := ST_ACTIVE
                        lastQualityScore := qualityScore(p31Dir)
                        p31ConfTier := confidenceTier(p31Dir)
                        if p31Dir == 1
                            strategy.entry("P31", strategy.long, comment = "L")
                        else
                            strategy.entry("P31", strategy.short, comment = "S")
                    else
                        p31State := ST_IDLE
                        p31Dir := 0
                else
                    p31State := ST_IDLE
                    p31Dir := 0""",
    )
    text = text.replace(
        """            if impulsePass
                if rDir == 1
                    seenRl := true
                    strategy.entry(oid, strategy.long, comment = "RL")
                else
                    seenRs := true
                    strategy.entry(oid, strategy.short, comment = "RS")
                strategy.exit("X" + oid, oid, stop = st, limit = tg)
                array.push(rvOpen, RvOpenTrade.new(rDir, px, st, tg, 0, bar_index, oid))""",
        """            if impulsePass
                if qualityPass(rDir)
                    if rDir == 1
                        seenRl := true
                        strategy.entry(oid, strategy.long, comment = "RL")
                    else
                        seenRs := true
                        strategy.entry(oid, strategy.short, comment = "RS")
                    lastQualityScore := qualityScore(rDir)
                    rvConfTier := confidenceTier(rDir)
                    strategy.exit("X" + oid, oid, stop = st, limit = tg)
                    array.push(rvOpen, RvOpenTrade.new(rDir, px, st, tg, 0, bar_index, oid))""",
    )

    return text + "\n"


def patch_strategy(src: str) -> str:
    temp = src.replace("strategy(", "indicator(", 1)
    text = patch_indicator(temp)
    text = text.replace("indicator(", "strategy(", 1)
    text = text.replace(
        "// NQ 15m Combined Strategy — Phase 40 Impulse Filter",
        "// NQ 15m Combined Strategy — Phase 44 Quality Filter",
    )
    text = text.replace(
        '     "NQ 15M Combined Phase 40 Impulse Filter Strategy"',
        '     "NQ 15M Combined Phase 44 Quality Filter Strategy"',
    )
    text = text.replace('shorttitle = "NQ15_P40_ST"', 'shorttitle = "NQ15_P44_ST"')
    text = text.replace("pyramiding = 10", "pyramiding = 0")
    return text


def write_pine_files(output: Path, *, indicator_src: str, strategy_src: str) -> None:
    (output / "NQ15_PHASE44_QUALITY_INDICATOR.pine").write_text(patch_indicator(indicator_src))
    (output / "NQ15_PHASE44_QUALITY_STRATEGY.pine").write_text(patch_strategy(strategy_src))
