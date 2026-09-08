# Trigger NinjaTrader NinjaScript compile (F5) after indicator file changes
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$SourceCs = Join-Path $RepoRoot "phase74\market_data\ninjatrader\CRTBarBridge.cs"

& (Join-Path $PSScriptRoot "setup-ninjatrader-bridge.ps1") | Out-Null

Copy-Item -Force $SourceCs (Join-Path $env:USERPROFILE "OneDrive\Documents\NinjaTrader 8\bin\Custom\Indicators\CRTBarBridge.cs")
Copy-Item -Force $SourceCs (Join-Path $env:USERPROFILE "Documents\NinjaTrader 8\bin\Custom\Indicators\CRTBarBridge.cs")

Add-Type @"
using System;
using System.Runtime.InteropServices;
public class WinActivate {
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
}
"@

$nt = Get-Process NinjaTrader -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $nt) {
    Write-Host "NinjaTrader is not running. Start NT8, open NinjaScript Editor, then re-run." -ForegroundColor Yellow
    exit 1
}

[WinActivate]::ShowWindow($nt.MainWindowHandle, 9) | Out-Null
[WinActivate]::SetForegroundWindow($nt.MainWindowHandle) | Out-Null
Start-Sleep -Milliseconds 800
$wshell = New-Object -ComObject WScript.Shell
$wshell.SendKeys('{F5}')
Write-Host "Sent F5 compile to NinjaTrader. Check NinjaScript Output for errors." -ForegroundColor Green
