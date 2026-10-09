# Run Python ledger validation on a real TradingView GLD export CSV
param(
    [Parameter(Mandatory = $true)]
    [string]$CsvPath
)

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$csv = Resolve-Path $CsvPath
$outDir = Join-Path $RepoRoot "signal_ledger\output"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

Write-Host "=== Ledger export checks ===" -ForegroundColor Cyan
Write-Host "CSV: $csv"

Write-Host "`n[1/2] recompute_gate_offsets..." -ForegroundColor Yellow
& $python signal_ledger/tools/recompute_gate_offsets.py `
    --gate-export $csv `
    --out-csv (Join-Path $outDir "GATE_KNOWN_AT_OFFSETS.csv") `
    --out-json (Join-Path $outDir "PIVOT_LAG_CHECK.json")

Write-Host "`n[2/2] cold-start tri-state scan..." -ForegroundColor Yellow
& $python -c @"
from pathlib import Path
import pandas as pd
from signal_ledger.gate_export import load_tv_gate_export
from signal_ledger.gate_tri_state import gate_state_detail_from_export_row

path = Path(r'$($csv.Path)')
df = load_tv_gate_export(path)
cold = 0
for _, row in df.iterrows():
    d = gate_state_detail_from_export_row(row)
    states = {d['evidence_threshold_long_state'], d['evidence_threshold_short_state'],
              d['arm_total_long_state'], d['arm_total_short_state']}
    if 'insufficient_warmup' in states:
        cold += 1
prc = df.get('pass_reason_code', pd.Series(dtype=float))
htf = df.get('htf_warmup_ready', pd.Series(dtype=bool))
print('bars_total', len(df))
print('bars_any_insufficient_warmup', cold)
print('bars_pass_reason_code_1', int((prc == 1).sum()) if len(prc) else 0)
print('bars_htf_warmup_ready_false', int((htf == False).sum()) if len(htf) else 0)
print('gld_columns', sum(1 for c in df.columns if str(c).startswith('GLD_')))
"@

Write-Host "`nDone. Outputs in signal_ledger/output/" -ForegroundColor Green
