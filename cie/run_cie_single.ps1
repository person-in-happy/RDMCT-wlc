param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('check','smoke','gpu-smoke','model-evidence','generate-validation','generate-core','generate-sensitivity','generate-ood','generate-all','warmstarts-core','warmstarts-sensitivity','warmstarts-ood','train-hem','train-feature-only','train-proposed','train-all','freeze-checkpoints','tune-acs','benchmark-validation','benchmark-main','benchmark-stability','benchmark-doe','benchmark-spbs','benchmark-sensitivity','benchmark-ood','analyze')]
    [string]$Stage,
    [string]$Seeds = '1,2,3,4,5,6,7,8,9,10',
    [int]$TimeLimit = 600,
    [int]$WarmStartTimeLimit = 180,
    [string]$GpuDevice = 'cuda:0',
    [int]$MaxInstances = 0,
    [ValidateRange(512,65536)]
    [int]$MemoryLimitMB = 4096,
    [ValidatePattern('^[A-Za-z0-9_-]*$')]
    [string]$CampaignId = '',
    [ValidatePattern('^[A-Za-z0-9_-]*$')]
    [string]$ShardTag = '',
    [ValidatePattern('^[A-Za-z0-9_-]*$')]
    [string]$LogId = '',
    [ValidatePattern('^[0-9, ]*$')]
    [string]$TrainingSeeds = '',
    [ValidateSet('both','none','auto')]
    [string]$SpbsWarmStarts = 'both',
    [string]$AnalysisInput = 'cie/results',
    [string]$AnalysisOutput = 'cie/results/analysis',
    [string]$ReferenceMethod = 'proposed',
    [string]$AcsWeightsFile = '',
    [string]$CheckpointManifest = 'cie/results/repro_manifest/selected_checkpoint_manifest.csv',
    [switch]$AllowLegacyCheckpoints
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path $PSScriptRoot -Parent
$Runner = Join-Path $PSScriptRoot 'run_cie.ps1'
Set-Location $RepoRoot

& python -c "import sys; print(sys.executable)" 1>$null 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Activate a Python environment with the project dependencies first.' }
if ($env:PYTORCH_CUDA_ALLOC_CONF -match 'expandable_segments') { Remove-Item Env:PYTORCH_CUDA_ALLOC_CONF }

if (-not $LogId) {
    if ($CampaignId -and $ShardTag) { $LogId = "${CampaignId}_${ShardTag}" }
    elseif ($CampaignId) { $LogId = $CampaignId }
    else { $LogId = "${Stage}_$(Get-Date -Format 'yyyyMMdd_HHmmss')" }
}
$logRoot = Join-Path $RepoRoot "cie\results\logs\$LogId"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$stdout = Join-Path $logRoot 'run.out.log'
$stderr = Join-Path $logRoot 'run.err.log'

try { $availableMB = [math]::Floor((Get-Counter '\Memory\Available MBytes' -ErrorAction Stop).CounterSamples[0].CookedValue) } catch { $availableMB = -1 }
if ($availableMB -ge 0 -and $availableMB -lt ($MemoryLimitMB + 1024)) { Write-Warning "Low available RAM: ${availableMB}MB. Close memory-heavy applications if the run becomes slow or reaches a memory limit." }

$arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',$Runner,'-Stage',$Stage,'-Seeds',$Seeds,'-TimeLimit',$TimeLimit.ToString(),'-WarmStartTimeLimit',$WarmStartTimeLimit.ToString(),'-GpuDevice',$GpuDevice,'-MaxInstances',$MaxInstances.ToString(),'-MemoryLimitMB',$MemoryLimitMB.ToString(),'-SpbsWarmStarts',$SpbsWarmStarts,'-AnalysisInput',$AnalysisInput,'-AnalysisOutput',$AnalysisOutput,'-ReferenceMethod',$ReferenceMethod)
$arguments += @('-CheckpointManifest', $CheckpointManifest)
if ($CampaignId) { $arguments += @('-CampaignId', $CampaignId) }
if ($ShardTag) { $arguments += @('-ShardTag', $ShardTag) }
if ($TrainingSeeds) { $arguments += @('-TrainingSeeds', $TrainingSeeds) }
if ($AcsWeightsFile) { $arguments += @('-AcsWeightsFile', $AcsWeightsFile) }
if ($AllowLegacyCheckpoints) { $arguments += '-AllowLegacyCheckpoints' }

$powerShellExe = (Get-Process -Id $PID).Path
$process = Start-Process -FilePath $powerShellExe -ArgumentList $arguments -WorkingDirectory $RepoRoot -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -NoNewWindow
$null = $process.Handle
$startedAt = Get-Date
$lastPercent = 0

function Get-Percent {
    param([string]$Path, [string]$JobStage, [bool]$Exited, [int]$Previous, [string]$SelectedTrainingSeeds, [string]$SelectedSpbsWarmStarts)
    if ($Exited) { return 100 }
    if (-not (Test-Path -LiteralPath $Path)) { return $Previous }
    try {
        $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        try {
            $reader = New-Object System.IO.StreamReader($stream, $true)
            try { $text = $reader.ReadToEnd() } finally { $reader.Dispose() }
        } finally { $stream.Dispose() }
    } catch { return $Previous }
    $matches = [regex]::Matches($text, '(?m)^\[(\d+)/(\d+)\]')
    if ($matches.Count -eq 0) { return $Previous }
    $completed = 0
    $current = 0
    $firstTotal = [int]$matches[0].Groups[2].Value
    foreach ($match in $matches) {
        $value = [int]$match.Groups[1].Value
        if ($value -le $current) { $completed += $current; $current = 0 }
        if ($value -gt $current) { $current = $value }
    }
    $done = $completed + $current
    if ($JobStage -in @('benchmark-main','benchmark-ood')) {
        $selected = if ([string]::IsNullOrWhiteSpace($SelectedTrainingSeeds)) { @(1,2,3,4,5) } else { @($SelectedTrainingSeeds -split ',' | ForEach-Object { [int]$_.Trim() }) }
        if ($selected -contains 1) {
            $expected = $firstTotal + [math]::Max(0, $selected.Count - 1) * [math]::Round(($firstTotal / 7.0) * 5.0)
        } else {
            $expected = $firstTotal * $selected.Count
        }
    } elseif ($JobStage -eq 'benchmark-stability') {
        $selected = if ([string]::IsNullOrWhiteSpace($SelectedTrainingSeeds)) { @(1,2,3,4,5) } else { @($SelectedTrainingSeeds -split ',' | ForEach-Object { [int]$_.Trim() }) }
        $expected = 3 * $selected.Count * $firstTotal
    } elseif ($JobStage -eq 'benchmark-spbs') { $expected = $(if ($SelectedSpbsWarmStarts -eq 'both') { 2 * $firstTotal } else { $firstTotal }) } else { $expected = [math]::Max($firstTotal, $done) }
    return [math]::Max($Previous, [math]::Min(99, [math]::Floor(100.0 * $done / [math]::Max(1, $expected))))
}

function Stop-CieProcessTree {
    param([int]$RootProcessId)
    $allProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
    $pending = @($RootProcessId)
    $descendants = @()
    while ($pending.Count -gt 0) {
        $parents = @($pending)
        $pending = @()
        foreach ($candidate in $allProcesses) {
            if ($parents -contains [int]$candidate.ParentProcessId) {
                $childId = [int]$candidate.ProcessId
                if ($descendants -notcontains $childId) {
                    $descendants += $childId
                    $pending += $childId
                }
            }
        }
    }
    [array]::Reverse($descendants)
    foreach ($childId in $descendants) {
        Stop-Process -Id $childId -Force -ErrorAction SilentlyContinue
    }
    Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue
}

try {
while (-not $process.HasExited) {
    $process.Refresh()
    $lastPercent = Get-Percent -Path $stdout -JobStage $Stage -Exited $false -Previous $lastPercent -SelectedTrainingSeeds $TrainingSeeds -SelectedSpbsWarmStarts $SpbsWarmStarts
    $elapsed = (Get-Date) - $startedAt
    $etaText = '--:--:--'
    if ($lastPercent -gt 0) {
        $remainingSeconds = [math]::Max(0, $elapsed.TotalSeconds * (100 - $lastPercent) / $lastPercent)
        $etaText = [TimeSpan]::FromSeconds($remainingSeconds).ToString('hh\:mm\:ss')
    }
    Write-Progress -Activity "$Stage ($LogId)" -Status "$lastPercent% | elapsed $($elapsed.ToString('hh\:mm\:ss')) | ETA $etaText" -PercentComplete $lastPercent
    Start-Sleep -Seconds 5
}
} finally {
    if (-not $process.HasExited) {
        Write-Warning 'Interrupt received; stopping only this launcher process tree. The active atomic unit will be retried on resume.'
        Stop-CieProcessTree -RootProcessId $process.Id
        $null = $process.WaitForExit(10000)
    }
    Write-Progress -Activity $Stage -Completed
}
$process.WaitForExit()
$process.Refresh()
Write-Progress -Activity "$Stage ($LogId)" -Completed
if ($process.ExitCode -ne 0) {
    Write-Host "Failed. Logs: $stdout ; $stderr" -ForegroundColor Red
    if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Tail 12 }
    exit $process.ExitCode
}
Write-Host "Completed: $Stage" -ForegroundColor Green
Write-Host "Logs: $logRoot" -ForegroundColor DarkGray
