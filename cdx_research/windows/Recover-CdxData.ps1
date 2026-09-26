# CDX V3 Windows data recovery. Does not modify Phase72A/73/74/85 or CRTBarBridge.
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$ErrorActionPreference = "Stop"
# this file lives at cdx_research/windows/
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

$present = [string]::IsNullOrWhiteSpace($env:DATABENTO_API_KEY) -eq $false
Write-Host ("DATABENTO_API_KEY_PRESENT=" + ($(if ($present) { "true" } else { "false" })))

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command python3 -ErrorAction SilentlyContinue }
if (-not $py) { throw "python not found on PATH" }

& $py.Source -m cdx_research.python.recover_windows
$code = $LASTEXITCODE

$ntSrc = Join-Path $RepoRoot "cdx_research\ninjatrader\CDXHistoricalBarExport.cs"
$indDirs = @(
    (Join-Path $env:USERPROFILE "Documents\NinjaTrader 8\bin\Custom\Indicators"),
    (Join-Path $env:USERPROFILE "OneDrive\Documents\NinjaTrader 8\bin\Custom\Indicators")
)
foreach ($d in $indDirs) {
    if (Test-Path (Split-Path (Split-Path $d -Parent) -Parent)) {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Copy-Item -Force $ntSrc (Join-Path $d "CDXHistoricalBarExport.cs")
        Write-Host "Installed CDXHistoricalBarExport.cs -> $d"
    }
}

if ($code -ne 0) {
    Write-Host ""
    Write-Host "If Databento is unavailable, complete Path B:"
    Write-Host "  1. NinjaTrader 8 is running."
    Write-Host "  2. NinjaScript Editor -> compile (F5)."
    Write-Host "  3. Open NQ 1-minute ELECTRONIC/ETH session (not RTH-only)."
    Write-Host "  4. Days to load >= 30. Chart timezone must match ChartTimeZoneId (default Eastern)."
    Write-Host "  5. Add indicator CDXHistoricalBarExport. Wait until it prints closed rows=..."
    Write-Host "  6. Re-run this script. It will pick up Documents\\NinjaTrader 8\\cdx_export\\nq_1m_ninjatrader_sep6_sep21.csv"
    Write-Host "Do not merge that file into phase58j. Do not label it DATABENTO."
}

exit $code
