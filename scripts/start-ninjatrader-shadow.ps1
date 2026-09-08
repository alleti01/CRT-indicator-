# Start Phase74 shadow bot with NinjaTrader bar bridge + webhook
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $RepoRoot "phase74\.env"

if (-not (Test-Path $envFile)) {
    Write-Host "Missing phase74\.env — run .\scripts\setup-ninjatrader-bridge.ps1 first" -ForegroundColor Red
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

Write-Host "Starting NinjaTrader shadow bot (port 8765 bridge, 8787 webhook)..." -ForegroundColor Cyan
Write-Host "Webhook URL: http://127.0.0.1:8787/webhook?token=$env:PHASE74_WEBHOOK_SECRET"
& $python phase74\run_live.py --provider ninjatrader --mode shadow --webhook --bars 120
