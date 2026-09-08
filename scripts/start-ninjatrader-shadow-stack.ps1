# Full stack: sync NT bridge files, start shadow bot, verify ports (ngrok assumed already running)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

& (Join-Path $PSScriptRoot "setup-ninjatrader-bridge.ps1")

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$existing = Get-NetTCPConnection -LocalPort 8765,8787 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $pids = $existing.OwningProcess | Sort-Object -Unique
    foreach ($pid in $pids) {
        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq "python") {
            Write-Host "Stopping existing shadow bot (PID $pid)..." -ForegroundColor Yellow
            Stop-Process -Id $pid -Force
        }
    }
    Start-Sleep -Seconds 1
}

Set-Location $RepoRoot
Write-Host "`nStarting shadow bot in background..." -ForegroundColor Cyan
Start-Process -FilePath $python -ArgumentList "phase74\run_live.py", "--provider", "ninjatrader", "--mode", "shadow", "--webhook", "--bars", "120" -WorkingDirectory $RepoRoot -WindowStyle Hidden

$deadline = (Get-Date).AddSeconds(15)
$ready = $false
while ((Get-Date) -lt $deadline) {
    $listeners = @(Get-NetTCPConnection -LocalPort 8765,8787 -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -ge 2) {
        $ready = $true
        break
    }
    Start-Sleep -Milliseconds 500
}

Write-Host "`n=== Stack status ===" -ForegroundColor Cyan
foreach ($port in 8765, 8787) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        Write-Host "Port $port LISTEN (PID $($conn.OwningProcess))" -ForegroundColor Green
    } else {
        Write-Host "Port $port NOT listening" -ForegroundColor Red
    }
}

try {
    $tunnels = (Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -TimeoutSec 3).tunnels
    foreach ($t in $tunnels) {
        Write-Host "ngrok: $($t.public_url) -> $($t.config.addr)" -ForegroundColor Green
    }
} catch {
    Write-Host "ngrok: not detected on localhost:4040 (start manually if needed)" -ForegroundColor Yellow
}

if ($ready) {
    Write-Host "`nBridge ready. If NinjaTrader chart has CRTBarBridge, it should connect within ~60s." -ForegroundColor Green
    Write-Host "Watch bot stdout in Task Manager python process or re-run without -WindowStyle Hidden for logs." -ForegroundColor Yellow
} else {
    Write-Host "`nBot may still be starting - check python process and phase74/logs/errors.csv" -ForegroundColor Yellow
}
