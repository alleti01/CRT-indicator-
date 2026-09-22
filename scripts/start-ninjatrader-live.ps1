# Phase74 paper journal + Phase85 NT FUNDED execution (1 NQ eval).
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $RepoRoot "phase74\.env"

if (-not (Test-Path $envFile)) {
    Write-Host "Missing phase74\.env - run .\scripts\setup-ninjatrader-bridge.ps1 first" -ForegroundColor Red
    exit 1
}

function Set-EnvKey {
    param([string]$Path, [string]$Key, [string]$Value)
    $lines = @(Get-Content -Path $Path)
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match "^$([regex]::Escape($Key))=") {
            $found = $true
            "$Key=$Value"
        } else {
            $line
        }
    }
    if (-not $found) { $out += "$Key=$Value" }
    Set-Content -Path $Path -Value $out -Encoding UTF8
}

function New-RandomToken {
    param([int]$Length = 48)
    $chars = (48..57) + (65..90) + (97..122) | ForEach-Object { [char]$_ }
    -join (1..$Length | ForEach-Object { $chars | Get-Random })
}

Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*([^#=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim(), 'Process')
    }
}

if (-not $env:NINJATRADER_EXECUTION_BRIDGE_TOKEN) {
    $execToken = New-RandomToken
    Set-EnvKey -Path $envFile -Key "NINJATRADER_EXECUTION_BRIDGE_TOKEN" -Value $execToken
    $env:NINJATRADER_EXECUTION_BRIDGE_TOKEN = $execToken
}

$account = "TDFYSL50366329071"
$contract = "NQ 12-26"
Set-EnvKey -Path $envFile -Key "EXPECTED_ACCOUNT" -Value $account
Set-EnvKey -Path $envFile -Key "ALLOWED_FUNDED_ACCOUNT" -Value $account
Set-EnvKey -Path $envFile -Key "EXPECTED_CONTRACT" -Value $contract
Set-EnvKey -Path $envFile -Key "FUNDED_ACCOUNT_VERIFIED" -Value "true"
$env:EXPECTED_ACCOUNT = $account
$env:ALLOWED_FUNDED_ACCOUNT = $account
$env:EXPECTED_CONTRACT = $contract
$env:FUNDED_ACCOUNT_VERIFIED = "true"
$env:EXECUTION_MODE = "FUNDED"
$env:SHADOW_MODE = "false"
$env:TRADING_ENABLED = "true"
$env:EXTERNAL_ORDER_ROUTING = "true"
$env:NT_EXECUTION_BRIDGE_ENABLED = "true"

$customDirs = @(
    (Join-Path $env:USERPROFILE "OneDrive\Documents\NinjaTrader 8\bin\Custom"),
    (Join-Path $env:USERPROFILE "Documents\NinjaTrader 8\bin\Custom")
) | Where-Object { Test-Path $_ }
foreach ($custom in $customDirs) {
    Set-Content -Path (Join-Path $custom "crt_execution_token.txt") -Value $env:NINJATRADER_EXECUTION_BRIDGE_TOKEN -Encoding ASCII -NoNewline
    Write-Host "Wrote execution token file under $custom" -ForegroundColor Green
}

Set-Location $RepoRoot
$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

$existing = Get-NetTCPConnection -LocalPort 8765,8766,8787 -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $pids = $existing.OwningProcess | Sort-Object -Unique
    foreach ($procId in $pids) {
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        if ($proc -and $proc.ProcessName -eq "python") {
            Write-Host "Stopping existing bot (PID $procId)..." -ForegroundColor Yellow
            Stop-Process -Id $procId -Force
        }
    }
    Start-Sleep -Seconds 2
}

Write-Host "Starting LIVE stack: 1 NQ FUNDED eval $account / $contract" -ForegroundColor Cyan
& $python phase74\run_live.py --provider ninjatrader --mode live --webhook --bars 0
