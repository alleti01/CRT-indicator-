#!/usr/bin/env python3
"""Build phase72a_autonomous_trader.pine from Phase59 signal stack + Phase60 HTF + Phase71 mgmt."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "TV_REVIEW" / "phase59_canonical_live.pine"
OUT = ROOT / "TV_REVIEW" / "phase72a_autonomous_trader.pine"

HTF_REPLACEMENT = r'''
// =============================================================================
// PHASE72A — Causal developing HTF (NO lookahead_on)
// Matches phase60/python/developing_htf.py semantics on 1M chart.
// Developing OHLC: incremental bucket state. Completed HTF: lookahead_off only.
// =============================================================================

// ── Developing 5M bucket ─────────────────────────────────────────────────────
var int   m5BucketMs = na
var float m5Open = na
var float m5High = na
var float m5Low  = na
var float m5Close = na
var float m5PrevClose = na
var float m5PrevHigh = na
var float m5PrevLow = na

bucket5Ms = int(time / 300000) * 300000
newM5 = na(m5BucketMs) or bucket5Ms != m5BucketMs
if newM5
    m5PrevClose := m5Close
    m5PrevHigh := m5High
    m5PrevLow := m5Low
    m5BucketMs := bucket5Ms
    m5Open := open
    m5High := high
    m5Low := low
    m5Close := close
else
    m5High := math.max(m5High, high)
    m5Low := math.min(m5Low, low)
    m5Close := close

// ── Developing 15M bucket ────────────────────────────────────────────────────
var int   m15BucketMs = na
var float m15Open = na
var float m15High = na
var float m15Low  = na
var float m15Close = na
var float m15PrevClose = na

bucket15Ms = int(time / 900000) * 900000
newM15 = na(m15BucketMs) or bucket15Ms != m15BucketMs
if newM15
    m15PrevClose := m15Close
    m15BucketMs := bucket15Ms
    m15Open := open
    m15High := high
    m15Low := low
    m15Close := close
else
    m15High := math.max(m15High, high)
    m15Low := math.min(m15Low, low)
    m15Close := close

// Aliases — signal engine uses m5H/m5L/m15H etc. (developing current bucket)
m5H  = m5High
m5L  = m5Low
m5C  = m5Close
m5O  = m5Open
m5C1 = m5PrevClose
m5H1 = m5PrevHigh
m5L1 = m5PrevLow
m15H = m15High
m15L = m15Low
m15C = m15Close
m15O = m15Open

// Completed HTF (confirmed bars only — lookahead_off)
[m5C_comp, m5O_comp, m5H_comp, m5L_comp] = request.security(
     syminfo.tickerid, "5", [close[1], open[1], high[1], low[1]], lookahead=barmerge.lookahead_off)
[m15C_comp, m15H_comp, m15L_comp] = request.security(
     syminfo.tickerid, "15", [close[1], high[1], low[1]], lookahead=barmerge.lookahead_off)
m5BarTime = request.security(syminfo.tickerid, "5", time[1], lookahead=barmerge.lookahead_off)
m15BarTime = request.security(syminfo.tickerid, "15", time[1], lookahead=barmerge.lookahead_off)

m5AtrRaw = ta.sma(m5H - m5L, 14)
m15AtrRaw = ta.sma(m15H - m15L, 14)
m5Atr  = f_atrUse(m5AtrRaw)
m15Atr = f_atrUse(m15AtrRaw)

// 5M swings — completed bars only
m5PivotH = request.security(syminfo.tickerid, "5", ta.pivothigh(high, swingPeriod, swingPeriod), lookahead=barmerge.lookahead_off)
m5PivotL = request.security(syminfo.tickerid, "5", ta.pivotlow(low, swingPeriod, swingPeriod), lookahead=barmerge.lookahead_off)
var float m5LastSH = na
var float m5PrevSH = na
var float m5LastSL = na
var float m5PrevSL = na
if not na(m5PivotH)
    m5PrevSH := m5LastSH
    m5LastSH := m5PivotH
if not na(m5PivotL)
    m5PrevSL := m5LastSL
    m5LastSL := m5PivotL

// 15M structural refs — completed bars only
m15H4 = request.security(syminfo.tickerid, "15", high[4], lookahead=barmerge.lookahead_off)
m15L4 = request.security(syminfo.tickerid, "15", low[4], lookahead=barmerge.lookahead_off)
m15C12 = request.security(syminfo.tickerid, "15", close[12], lookahead=barmerge.lookahead_off)

// HTF debug (known_at = current 1M bar close)
htfKnownAt = time
htfCompleted = false
htfTime5 = m5BucketMs
htfTime15 = m15BucketMs
'''

PHASE71_MGMT = r'''
// =============================================================================
// PHASE71 — Frozen one-position management (T5 + M0)
// Replaces overlapping M1 array trades. STOP_FIRST. T5 @ ei+15 once.
// =============================================================================
grpP71 = "Phase71 Management"
t5Bars      = input.int(15, "T5 checkpoint bars", group=grpP71)
t5MfeR      = input.float(1.0, "T5 MFE threshold R", group=grpP71)
enableT5    = input.bool(true, "Enable T5", group=grpP71)
DEBUG_MANUAL_SIGNAL = input.bool(false, "DEBUG manual signal override", group=grpP71)
debugManualLong  = input.bool(false, "Manual LONG signal", group=grpP71)
debugManualShort = input.bool(false, "Manual SHORT signal", group=grpP71)

var string posState = "FLAT"
var float  entryPx = na
var float  initAtr = na
var float  stopPx = na
var float  tgtPx = na
var int    entryBar = na
var int    signalBar = na
var int    posDir = 0
var float  runMfeR = 0.0
var bool   t5Checked = false
var string lastAction = ""
var string lastReason = ""
var int    skippedSignals = 0

f_posActive() =>
    posState == "LONG_ACTIVE" or posState == "SHORT_ACTIVE" or posState == "PENDING_LONG" or posState == "PENDING_SHORT"

'''

# Replace old trade-array management block
OLD_MGMT = re.compile(
    r"    // ── Manage M1 canonical trades \(entry bar excluded, stop before target\) ─\n"
    r"    tN = array\.size\(tActive\).*?"
    r"                            label\.new\(bar_index, close, \"TIME \" \+ dir,.*?\n"
    r"    \n",
    re.DOTALL,
)

NEW_MGMT = r'''    // ── Phase71 one-position management ─────────────────────────────────
    if posState == "PENDING_LONG" or posState == "PENDING_SHORT"
        if bar_index == signalBar + 1
            entryPx := open
            initAtr := atrUse
            entryBar := bar_index
            posDir := posState == "PENDING_LONG" ? 1 : -1
            risk = m1StopAtr * initAtr
            stopPx := posDir == 1 ? entryPx - risk : entryPx + risk
            tgtPx := posDir == 1 ? entryPx + targetR * risk : entryPx - targetR * risk
            runMfeR := 0.0
            t5Checked := false
            posState := posDir == 1 ? "LONG_ACTIVE" : "SHORT_ACTIVE"
            lastAction := posDir == 1 ? "ENTER_LONG" : "ENTER_SHORT"
            lastReason := "ENTRY"
            if showEntry
                label.new(bar_index, entryPx, "ENTER " + (posDir == 1 ? "LONG" : "SHORT"), style=posDir == 1 ? label.style_label_up : label.style_label_down, color=color.green, size=size.small)

    if posState == "LONG_ACTIVE" or posState == "SHORT_ACTIVE"
        mins = bar_index - entryBar
        risk = m1StopAtr * initAtr
        hitStop = posDir == 1 ? low <= stopPx : high >= stopPx
        hitTgt  = posDir == 1 ? high >= tgtPx : low <= tgtPx
        exited = false
        reason = ""
        if hitStop and hitTgt
            exited := true
            reason := "EXIT_STOP"
            lastAction := "EXIT_STOP"
            lastReason := "M0_STOP"
            if showExits
                label.new(bar_index, stopPx, "STOP", color=color.red, size=size.tiny)
        else if hitStop
            exited := true
            reason := "EXIT_STOP"
            lastAction := "EXIT_STOP"
            lastReason := "M0_STOP"
            if showExits
                label.new(bar_index, stopPx, "STOP", color=color.red, size=size.tiny)
        else if hitTgt
            exited := true
            reason := "EXIT_TARGET"
            lastAction := "EXIT_TARGET"
            lastReason := "M0_TARGET"
            if showExits
                label.new(bar_index, tgtPx, "TARGET", color=color.lime, size=size.tiny)
        if not exited
            fav = posDir == 1 ? (high - entryPx) / risk : (entryPx - low) / risk
            runMfeR := math.max(runMfeR, fav)
            if enableT5 and not t5Checked and mins >= t5Bars
                t5Checked := true
                if runMfeR < t5MfeR
                    exited := true
                    reason := "EXIT_TIME_PROGRESS"
                    lastAction := "EXIT_TIME_PROGRESS"
                    lastReason := "T5_NO_PROGRESS"
                    if showExits
                        label.new(bar_index, close, "T5", color=color.orange, size=size.tiny)
            if not exited and mins >= maxHoldBars
                exited := true
                reason := "EXIT_MAX_HOLD"
                lastAction := "EXIT_MAX_HOLD"
                lastReason := "MAX_HOLD_60M"
                if showExits
                    label.new(bar_index, close, "60M", color=color.gray, size=size.tiny)
        if exited
            posState := "FLAT"
            entryPx := na
            runMfeR := 0.0
            t5Checked := false
            posDir := 0

'''


def build() -> str:
    text = SRC.read_text()
    # Header
    text = text.replace(
        'indicator("Phase59H Canonical Live"',
        'indicator("Phase72A Autonomous Trader"',
    )
    text = re.sub(
        r"// PHASE59C —.*?// Primary chart: 1M NQ.*?\n",
        "// PHASE72A — Frozen causal signal (Phase60 HTF) + Phase71 management\n"
        "// Signal hash: 0da41f282174679f | Trader hash: b6adfc04e8885a3d\n"
        "// NO lookahead_on | One position | T5 @15m | STOP_FIRST\n",
        text,
        count=1,
        flags=re.DOTALL,
    )
    # Replace HTF block
    text = re.sub(
        r"// =============================================================================\n"
        r"// HTF — Python align_htf_to_1m parity.*?m15C12 = request\.security[^\n]+\n",
        HTF_REPLACEMENT.strip() + "\n",
        text,
        count=1,
        flags=re.DOTALL,
    )
    # Insert Phase71 vars before trade arrays
    insert_at = text.find("// ── M1 trade arrays")
    if insert_at == -1:
        insert_at = text.find("var array<int>    tEntryBar")
    if insert_at > 0:
        text = text[:insert_at] + PHASE71_MGMT + "\n" + text[insert_at:]
    # Patch pending entry to use Phase71 state
    text = text.replace(
        "    if pendingTake and bar_index == pendingSignalBar + 1\n"
        "        ep = open\n"
        "        f_addM1Trade(pendingDir, ep, bar_index)\n"
        "        f_dbgLogAutoEntry(pendingDir)\n"
        "        if showEntry\n"
        "            label.new(bar_index, ep, \"ENTRY \" + pendingDir + \"\\n\" + pendingOppId, style=pendingDir == \"LONG\" ? label.style_label_up : label.style_label_down, color=color.white, textcolor=color.black, size=size.small)\n"
        "        pendingTake := false\n"
        "        pendingDir := na\n"
        "        pendingSignalBar := na\n"
        "        pendingOppId := na\n",
        "    if pendingTake and bar_index == pendingSignalBar + 1\n"
        "        if posState == \"FLAT\"\n"
        "            posState := pendingDir == \"LONG\" ? \"PENDING_LONG\" : \"PENDING_SHORT\"\n"
        "            signalBar := pendingSignalBar\n"
        "        pendingTake := false\n"
        "        pendingDir := na\n"
        "        pendingSignalBar := na\n"
        "        pendingOppId := na\n",
    )
    # Replace M1 management loop
    text = OLD_MGMT.sub(NEW_MGMT, text, count=1)
    # Block signals when position active (one-position)
    text = text.replace(
        "    if not p58InTrade and p58State != 3 and not p58BlockSignals",
        "    if not f_posActive() and not p58InTrade and p58State != 3 and not p58BlockSignals",
    )
    # On canonical TAKE while position active — skip
    take_block = (
        "                            else\n"
        "                                // Canonical TAKE = Phase58D TAKE AND P4 KEEP AND H1 KEEP\n"
    )
    if take_block in text:
        text = text.replace(
            take_block,
            "                            else if f_posActive()\n"
            "                                skippedSignals += 1\n"
            "                                decisionLabel := \"SIGNAL_IGNORED\"\n"
            "                            else\n"
            "                                // Canonical TAKE = Phase58D TAKE AND P4 KEEP AND H1 KEEP\n",
        )
    # Fix HTF mode display in forensic table
    text = text.replace('"lookahead_on"', '"causal_dev"')
    text = text.replace("HTF mode", "HTF mode")
    text = text.replace('table.cell(h59Tbl, 1, 17, "lookahead_on"', 'table.cell(h59Tbl, 1, 17, "causal_dev"')
    # Debug manual override (must not affect unless DEBUG on)
    manual_hook = (
        "if barstate.isconfirmed and DEBUG_MANUAL_SIGNAL\n"
        "    if debugManualLong[1] and posState == \"FLAT\"\n"
        "        posState := \"PENDING_LONG\"\n"
        "        signalBar := bar_index - 1\n"
        "    if debugManualShort[1] and posState == \"FLAT\"\n"
        "        posState := \"PENDING_SHORT\"\n"
        "        signalBar := bar_index - 1\n"
    )
    text += "\n// DEBUG manual signal (disabled by default)\n" + manual_hook + "\n"
    return text


def main():
    out_text = build()
    OUT.write_text(out_text)
    h = hashlib.sha256(out_text.encode()).hexdigest()[:16]
    print(f"Wrote {OUT} ({len(out_text.splitlines())} lines)")
    print(f"PINE_HASH={h}")


if __name__ == "__main__":
    main()
