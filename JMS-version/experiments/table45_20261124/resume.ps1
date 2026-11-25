$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../../..')).Path
$python = 'G:/conda/python.exe'
$queue = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'queue_runs.py')).Path
$report = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'publish.py')).Path
$live = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'live_status.py')).Path
function Start-VisibleIfMissing([string]$scriptPath, [string]$mode) {
    $pattern = [regex]::Escape($scriptPath) + '"?\s+' + [regex]::Escape($mode) + '\s*$'
    $active = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match $pattern })
    if ($mode -in @('table4','table5') -and $active.Count -eq 1) {
        $campaign = if ($mode -eq 'table4') { 'table4_three_arms_20261124' } else { 'table5_one_percent_20261124' }
        $statusPath = Join-Path $root "JMS-version/results/$campaign/progress.json"
        if (Test-Path -LiteralPath $statusPath) {
            $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
            if ($status.pid -eq $active[0].ProcessId -and @($status.failures.PSObject.Properties).Count -gt 0) {
                # Retire the scheduler only. Its replacement adopts every active solver.
                Stop-Process -Id $active[0].ProcessId -ErrorAction Stop
                Wait-Process -Id $active[0].ProcessId -Timeout 10 -ErrorAction SilentlyContinue
                $active = @()
            }
        }
    }
    if ($active.Count -eq 0) {
        Start-Process -FilePath $python -ArgumentList @('-B','-u','-X','utf8',('"' + $scriptPath + '"'),$mode) -WorkingDirectory $root -WindowStyle Normal
    }
}
# A repeated resume also repairs a missing controller when the monitor is still open.
Start-Process -FilePath $python -ArgumentList @('-B','-u','-X','utf8',('"' + $live + '"'),'--resume') -WorkingDirectory $root -WindowStyle Normal
$legacyProgress = Join-Path $root 'JMS-version/results/table4_three_arms_20261124/progress.json'
if (Test-Path -LiteralPath $legacyProgress) {
    $legacy = Get-Content -Raw -LiteralPath $legacyProgress | ConvertFrom-Json
    if ($legacy.verified -lt $legacy.expected) {
        Start-VisibleIfMissing $queue 'table4'
        Start-VisibleIfMissing $report '--watch'
    }
}
