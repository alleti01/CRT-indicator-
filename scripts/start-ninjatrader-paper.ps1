# Phase74 local paper — real TV webhooks, NT bars, sequential sim fills + journal
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $RepoRoot "phase74\.env"

if (-not (Test-Path $envFile)) {
    Write-Host "Missing phase74\.env - run .\scripts\setup-ninjatrader-bridge.ps1 first" -ForegroundColor Red
    exit 1
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
    }
}

Set-Location $RepoRoot
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$existing = Get-NetTCPConnection -LocalPort 8765,8787 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $pids = $existing.OwningProcess | Sort-Object -Unique
    foreach ($procId in $pids) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq "python") {
            Write-Host "Stopping existing bot (PID $procId)..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force
        }
    }
    Start-Sleep -Seconds 1
}

Write-Host "Starting LOCAL PAPER bot (1-position, pass-chase/late ON, slippage sim)..." -ForegroundColor Cyan
Write-Host "  bars=0 -> run until Ctrl+C | logs: phase74/logs/paper_trades.csv + bars.csv"
$webhookUrl = "http://127.0.0.1:8787/webhook?token=$($env:PHASE74_WEBHOOK_SECRET)"
Write-Host "Webhook URL: $webhookUrl"
& $python phase74\run_live.py --provider ninjatrader --mode paper --webhook --bars 0
