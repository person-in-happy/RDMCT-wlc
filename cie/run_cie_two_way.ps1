param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('benchmark-main','benchmark-doe','benchmark-spbs','benchmark-sensitivity','benchmark-ood')]
    [string]$Stage,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$CampaignId,
    [Parameter(Mandatory = $true)]
    [string]$SeedsA,
    [Parameter(Mandatory = $true)]
    [string]$SeedsB,
    [int]$TimeLimit = 300,
    [ValidateRange(512,65536)]
    [int]$MemoryLimitMB = 4096,
    [string]$GpuDevice = 'cuda:0',
    [int]$MaxInstances = 0,
    [switch]$ForceLowMemory
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path $PSScriptRoot -Parent
$Runner = Join-Path $PSScriptRoot 'run_cie.ps1'

function Parse-Seeds {
    param([string]$Text)
    return @($Text -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

$parsedA = Parse-Seeds $SeedsA
$parsedB = Parse-Seeds $SeedsB
if ($parsedA.Count -eq 0 -or $parsedB.Count -eq 0) {
    throw 'Both seed shards must be non-empty.'
}
$overlap = @($parsedA | Where-Object { $parsedB -contains $_ })
if ($overlap.Count -gt 0) {
    throw "Solver-seed shards overlap: $($overlap -join ',')"
}

Set-Location $RepoRoot
& python -c "import sys; assert 'a3cenv' in sys.executable.lower(), sys.executable" 1>$null 2>$null
if ($LASTEXITCODE -ne 0) { throw 'Activate conda environment a3cenv first.' }
if ($env:PYTORCH_CUDA_ALLOC_CONF -match 'expandable_segments') {
    Remove-Item Env:PYTORCH_CUDA_ALLOC_CONF
    Write-Warning 'Removed PYTORCH_CUDA_ALLOC_CONF=expandable_segments because the Windows CUDA allocator does not support it.'
}

try {
    $availableMB = [math]::Floor((Get-Counter '\Memory\Available MBytes' -ErrorAction Stop).CounterSamples[0].CookedValue)
} catch {
    $availableMB = -1
}
$requiredMB = 2 * $MemoryLimitMB + 2048
if (-not $ForceLowMemory -and $availableMB -ge 0 -and $availableMB -lt $requiredMB) {
    throw "Unsafe two-way memory request: available=${availableMB}MB, estimated minimum=${requiredMB}MB (2 x solver limit plus 2048MB runtime reserve). Close memory-heavy applications, lower -MemoryLimitMB, run one shard at a time, or explicitly pass -ForceLowMemory."
}

# Use independent PowerShell processes with file-backed logs. Start-Job serializes
# every output line into remoting objects, which is expensive for verbose SCIP runs.
$logRoot = Join-Path $RepoRoot "cie\results\logs\$CampaignId"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$powerShellExe = (Get-Process -Id $PID).Path

function Start-ShardProcess {
    param([string]$Tag, [string]$JobSeeds)
    $stdout = Join-Path $logRoot "$Tag.out.log"
    $stderr = Join-Path $logRoot "$Tag.err.log"
    $arguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Runner,
        '-Stage', $Stage, '-Seeds', $JobSeeds,
        '-TimeLimit', $TimeLimit.ToString(), '-MemoryLimitMB', $MemoryLimitMB.ToString(),
        '-CampaignId', $CampaignId, '-ShardTag', $Tag,
        '-GpuDevice', $GpuDevice, '-MaxInstances', $MaxInstances.ToString()
    )
    $process = Start-Process -FilePath $powerShellExe -ArgumentList $arguments `
        -WorkingDirectory $RepoRoot -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr -PassThru -NoNewWindow
    # Cache the OS process handle now. On Windows PowerShell 5.1, ExitCode can
    # otherwise become null if a short-lived child exits before its handle is read.
    $null = $process.Handle
    return [pscustomobject]@{ Tag=$Tag; Process=$process; Stdout=$stdout; Stderr=$stderr }
}

function Get-LogProgress {
    param([string]$Path, [string]$JobStage, [bool]$Exited)
    if (-not (Test-Path -LiteralPath $Path)) { return $(if ($Exited) { 100 } else { 0 }) }
    # The benchmark runner emits one [completed/total] line per evaluation.
    # It restarts its counter for every training seed, so accumulate each run.
    try {
        $logText = [System.IO.File]::ReadAllText($Path)
    } catch {
        # The child may be flushing this file at the same instant; retry next tick.
        return 0
    }
    $matches = [regex]::Matches($logText, '(?m)^\[(\d+)/(\d+)\]')
    if ($matches.Count -eq 0) { return $(if ($Exited) { 100 } else { 0 }) }
    $completed = 0
    $current = 0
    $firstTotal = [int]$matches[0].Groups[2].Value
    foreach ($match in $matches) {
        $value = [int]$match.Groups[1].Value
        if ($value -le $current) {
            $completed += $current
            $current = 0
        }
        if ($value -gt $current) { $current = $value }
    }
    $done = $completed + $current
    if ($JobStage -in @('benchmark-main','benchmark-ood')) {
        # Five training seeds: seven methods for seed 1 and five for seeds 2--5.
        $expected = [math]::Round(($firstTotal / 7.0) * 27.0)
    } elseif ($JobStage -eq 'benchmark-spbs') {
        # SPBS runs the same evaluation set twice: without and with warm starts.
        $expected = 2 * $firstTotal
    } else {
        $expected = [math]::Max($firstTotal, $done)
    }
    if ($Exited) { return 100 }
    return [math]::Min(99, [math]::Floor(100.0 * $done / [math]::Max(1, $expected)))
}

$shards = @(
    Start-ShardProcess -Tag 'shardA' -JobSeeds $SeedsA
    Start-ShardProcess -Tag 'shardB' -JobSeeds $SeedsB
)
$startedAt = Get-Date
while (@($shards | Where-Object { -not $_.Process.HasExited }).Count -gt 0) {
    $progress = @()
    foreach ($shard in $shards) {
        $shard.Process.Refresh()
        $progress += Get-LogProgress -Path $shard.Stdout -JobStage $Stage -Exited $shard.Process.HasExited
    }
    $totalSeedCount = $parsedA.Count + $parsedB.Count
    $overall = [math]::Floor(($progress[0] * $parsedA.Count + $progress[1] * $parsedB.Count) / $totalSeedCount)
    $elapsed = (Get-Date) - $startedAt
    $etaText = '--:--:--'
    if ($overall -gt 0) {
        $remainingSeconds = [math]::Max(0, $elapsed.TotalSeconds * (100 - $overall) / $overall)
        $etaText = [TimeSpan]::FromSeconds($remainingSeconds).ToString('hh\:mm\:ss')
    }
    $status = "$overall% | A $($progress[0])% | B $($progress[1])% | elapsed $($elapsed.ToString('hh\:mm\:ss')) | ETA $etaText"
    Write-Progress -Activity "$Stage ($CampaignId)" -Status $status -PercentComplete $overall
    Start-Sleep -Seconds 5
}
Write-Progress -Activity "$Stage ($CampaignId)" -Completed
foreach ($shard in $shards) {
    $shard.Process.WaitForExit()
    $shard.Process.Refresh()
}
$failed = @($shards | Where-Object { $_.Process.ExitCode -ne 0 })
if ($failed.Count -gt 0) {
    foreach ($shard in $failed) {
        Write-Error "$($shard.Tag) failed with exit code $($shard.Process.ExitCode). See $($shard.Stderr) and $($shard.Stdout)"
    }
    throw "Parallel shard failure: $($failed.Tag -join ', ')"
}

$campaign = $Stage -replace '^benchmark-', ''
Write-Host "Two-way campaign completed: cie/results/$campaign/$CampaignId" -ForegroundColor Green
