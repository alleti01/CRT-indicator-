<#
Register the log sync to run every 30 minutes while you are logged in. Run once on the bot PC:

  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\install_log_sync_task.ps1

Remove it later with:  Unregister-ScheduledTask -TaskName "CRT bot log sync" -Confirm:$false
#>
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "sync_bot_logs.ps1"
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument ("-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"{0}`"" -f $script)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "CRT bot log sync" -Action $action -Trigger $trigger -Settings $settings `
    -Description "Push CRT bot logs and a health check to the bot-logs branch" -Force | Out-Null
Write-Host "Registered 'CRT bot log sync' (every 30 minutes). Running it once now..."
& $script
