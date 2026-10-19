<#
Push the live bot's logs and a health check to the `bot-logs` branch on GitHub.

Runs from Task Scheduler on the Windows bot PC (see install_log_sync_task.ps1).
It never touches the bot's own folder beyond reading log files: the copy and
the git work happen in a separate clone ($SyncDir), on a branch that holds
only logs. Account and fill files (phase85 audit) are never copied.

Manual run:
  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\sync_bot_logs.ps1
#>
param(
    [string]$RepoDir = (Split-Path -Parent $PSScriptRoot),
    [string]$SyncDir = (Join-Path $env:USERPROFILE "bot-log-sync"),
    [int]$StaleMinutes = 15
)

# git reports progress on stderr; Windows PowerShell 5.1 would treat that as fatal under "Stop".
$ErrorActionPreference = "Continue"
$Branch = "bot-logs"

# Market data and signal logs only. Paths are relative to the bot folder.
$Files = @(
    "phase74/logs/bars.csv",
    "phase74/logs/signals.jsonl",
    "phase74/logs/signals.csv",
    "phase74/logs/errors.jsonl",
    "phase74/logs/htf_bias.jsonl",
    "phase74/logs/quality_skips.csv",
    "cdx_vision/logs/vision_levels.jsonl"
)

function Write-SyncLog([string]$msg) {
    $line = "{0:u} {1}" -f (Get-Date).ToUniversalTime(), $msg
    Add-Content -Path (Join-Path $SyncDir "sync.log") -Value $line -ErrorAction SilentlyContinue
    Write-Host $line
}

function Get-LastTimestamp([string]$path, [string]$kind) {
    if (-not (Test-Path $path)) { return $null }
    $last = Get-Content -Path $path -Tail 1
    if (-not $last) { return $null }
    try {
        if ($kind -eq "csv") { return [DateTimeOffset]::Parse(($last -split ",")[0]) }
        $obj = $last | ConvertFrom-Json
        return [DateTimeOffset]::Parse($obj.received_at_utc)
    } catch { return $null }
}

function Test-MarketOpen([DateTimeOffset]$utc) {
    $tz = [TimeZoneInfo]::FindSystemTimeZoneById("Eastern Standard Time")
    $et = [TimeZoneInfo]::ConvertTime($utc, $tz)
    $d = $et.DayOfWeek
    $h = $et.Hour
    if ($d -eq "Saturday") { return $false }
    if ($d -eq "Friday" -and $h -ge 17) { return $false }
    if ($d -eq "Sunday" -and $h -lt 18) { return $false }
    if ($h -eq 17) { return $false }  # daily 5-6 pm ET break
    return $true
}

# ---------- first run: separate clone on the logs branch ----------
if (-not (Test-Path (Join-Path $SyncDir ".git"))) {
    $remote = (git -C $RepoDir remote get-url origin).Trim()
    git clone --quiet $remote $SyncDir
    git -C $SyncDir fetch --quiet origin $Branch 2>$null
    if ($LASTEXITCODE -eq 0) {
        git -C $SyncDir checkout --quiet -B $Branch "origin/$Branch"
    } else {
        git -C $SyncDir checkout --quiet --orphan $Branch
        git -C $SyncDir rm -rf --quiet . 2>$null
        Get-ChildItem -Path $SyncDir -Force | Where-Object { $_.Name -ne ".git" } | Remove-Item -Recurse -Force
    }
}

# Only this PC writes the logs branch; match the remote before adding to it.
git -C $SyncDir fetch --quiet origin $Branch 2>$null
if ($LASTEXITCODE -eq 0) { git -C $SyncDir reset --quiet --hard "origin/$Branch" }

# ---------- copy logs ----------
$copied = @()
foreach ($rel in $Files) {
    $src = Join-Path $RepoDir $rel
    if (Test-Path $src) {
        $dst = Join-Path $SyncDir $rel
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
        Copy-Item -Path $src -Destination $dst -Force
        $copied += $rel
    }
}

# ---------- health check ----------
$now = [DateTimeOffset]::UtcNow
$lastBar = Get-LastTimestamp (Join-Path $RepoDir "phase74/logs/bars.csv") "csv"
$lastSignal = Get-LastTimestamp (Join-Path $RepoDir "phase74/logs/signals.jsonl") "json"
$open = Test-MarketOpen $now
$barAge = if ($lastBar) { [math]::Round(($now - $lastBar).TotalMinutes, 1) } else { $null }
$bot = @(Get-CimInstance Win32_Process -Filter "Name LIKE 'python%'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match "run_live" })

$problems = @()
if ($bot.Count -eq 0) { $problems += "BOT_NOT_RUNNING" }
if ($open -and ($null -eq $barAge -or $barAge -gt $StaleMinutes)) { $problems += "BARS_STALE" }

$health = [ordered]@{
    checked_at_utc   = $now.ToString("o")
    market_open      = $open
    bot_running      = ($bot.Count -gt 0)
    last_bar_utc     = if ($lastBar) { $lastBar.ToString("o") } else { $null }
    bar_age_minutes  = $barAge
    last_signal_utc  = if ($lastSignal) { $lastSignal.ToString("o") } else { $null }
    status           = if ($problems.Count) { "PROBLEM" } else { "OK" }
    problems         = $problems
    files            = $copied
}
[IO.File]::WriteAllText((Join-Path $SyncDir "health.json"), ($health | ConvertTo-Json))  # no BOM

$history = Join-Path $SyncDir "health_history.csv"
if (-not (Test-Path $history)) { "checked_at_utc,status,problems,bar_age_minutes,bot_running,market_open" | Set-Content $history }
"{0},{1},{2},{3},{4},{5}" -f $health.checked_at_utc, $health.status, ($problems -join ";"), $barAge, $health.bot_running, $open | Add-Content $history

# ---------- commit and push ----------
git -C $SyncDir add -A
git -C $SyncDir diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git -C $SyncDir -c user.name="bot-pc" -c user.email="bot-pc@localhost" commit --quiet -m ("Bot logs {0:yyyy-MM-dd HH:mm} UTC, {1}" -f $now.UtcDateTime, $health.status)
    git -C $SyncDir push --quiet origin $Branch
    if ($LASTEXITCODE -ne 0) { Write-SyncLog "push failed"; exit 1 }
    Write-SyncLog ("pushed {0} files, status {1} {2}" -f $copied.Count, $health.status, ($problems -join ","))
} else {
    Write-SyncLog "no changes"
}
