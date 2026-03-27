param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptPath = "D:\cbc\hzw\bot_cursor_agent.py"

if (-not (Test-Path -LiteralPath $scriptPath)) {
    throw "Script not found: $scriptPath"
}

$pythonCmd = Get-Command python -ErrorAction Stop
$pythonExe = $pythonCmd.Source

$targets = @(
    "python D:\cbc\hzw\bot_cursor_agent.py --chat_by tg",
    "python D:\cbc\hzw\bot_cursor_agent.py --chat_by feishu"
)

function Stop-MatchedPythonProcesses {
    param(
        [string[]]$Patterns,
        [switch]$DryRunMode
    )

    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match "^python(\.exe)?$" -and $_.CommandLine
    }

    foreach ($p in $processes) {
        foreach ($pattern in $Patterns) {
            if ($p.CommandLine -like "*$pattern*") {
                if ($DryRunMode) {
                    Write-Host "[DryRun] Will stop PID=$($p.ProcessId) CommandLine=$($p.CommandLine)"
                }
                else {
                    Write-Host "Stopping PID=$($p.ProcessId) ..."
                    Stop-Process -Id $p.ProcessId -Force
                }
                break
            }
        }
    }
}

function Start-BotService {
    param(
        [string]$ChatBy,
        [switch]$DryRunMode
    )

    $args = @($scriptPath, "--chat_by", $ChatBy)
    if ($DryRunMode) {
        Write-Host "[DryRun] Will start: $pythonExe $($args -join ' ')"
        return
    }

    $proc = Start-Process -FilePath $pythonExe -ArgumentList $args -PassThru -WindowStyle Hidden
    Write-Host "Started [$ChatBy] PID=$($proc.Id)"
}

Write-Host "Cleaning old bot processes..."
Stop-MatchedPythonProcesses -Patterns $targets -DryRunMode:$DryRun

Write-Host "Starting bot services..."
Start-BotService -ChatBy "tg" -DryRunMode:$DryRun
Start-BotService -ChatBy "feishu" -DryRunMode:$DryRun

Write-Host "Done."
