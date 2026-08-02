param(
    [int]$TimeLimit = 3600,
    [ValidateRange(512,65536)]
    [int]$MemoryLimitMB = 2048,
    [int]$SeedA = 1,
    [int]$SeedB = 2,
    [string]$RunId = 'ood_missing_parallel_v1'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot
& python -c "import sys; assert 'a3cenv' in sys.executable.lower(), sys.executable"
if ($LASTEXITCODE -ne 0) { throw 'Activate conda environment a3cenv first.' }

$availableMB = [math]::Floor((Get-Counter '\Memory\Available MBytes').CounterSamples[0].CookedValue)
$requiredMB = 2 * $MemoryLimitMB + 2048
if ($availableMB -lt $requiredMB) {
    throw "Parallel recovery requires ${requiredMB}MB available; found ${availableMB}MB."
}

$instances = @(
    @{Tag='ood48_1to3'; Path='cie/data/ood/spbs/cie_ood_n048_f012_m036_proc100.lp'; Seed=$SeedA},
    @{Tag='ood64_1to3'; Path='cie/data/ood/spbs/cie_ood_n064_f016_m048_proc100.lp'; Seed=$SeedB}
)
$logRoot = Join-Path $RepoRoot "cie\results\logs\$RunId"
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$runs = @()
foreach ($item in $instances) {
    $stdout = Join-Path $logRoot "$($item.Tag).out.log"
    $stderr = Join-Path $logRoot "$($item.Tag).err.log"
    $arguments = @('cie/code/generate_one_warm_start.py','--instance',$item.Path,'--time_limit',$TimeLimit.ToString(),'--memory_limit_mb',$MemoryLimitMB.ToString(),'--random_seed',$item.Seed.ToString())
    $process = Start-Process -FilePath 'python' -ArgumentList $arguments -WorkingDirectory $RepoRoot -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -NoNewWindow
    $null = $process.Handle
    $runs += [pscustomobject]@{Tag=$item.Tag;Process=$process;Stdout=$stdout;Stderr=$stderr}
}

$started = Get-Date
while (@($runs | Where-Object {-not $_.Process.HasExited}).Count -gt 0) {
    foreach ($run in $runs) { $run.Process.Refresh() }
    $elapsed = ((Get-Date) - $started).TotalSeconds
    $percent = [math]::Min(99, [math]::Floor(100 * $elapsed / [math]::Max(1,$TimeLimit)))
    $status = ($runs | ForEach-Object { "$($_.Tag)=" + $(if ($_.Process.HasExited) {'done'} else {'running'}) }) -join ' | '
    Write-Progress -Activity "OOD missing warm starts ($RunId)" -Status "$status | elapsed $([TimeSpan]::FromSeconds($elapsed).ToString('hh\:mm\:ss'))" -PercentComplete $percent
    Start-Sleep -Seconds 5
}
Write-Progress -Activity "OOD missing warm starts ($RunId)" -Completed
foreach ($run in $runs) { $run.Process.WaitForExit(); $run.Process.Refresh() }
$failed = @($runs | Where-Object {$_.Process.ExitCode -ne 0})
if ($failed.Count -gt 0) {
    foreach ($run in $failed) { Write-Host "$($run.Tag) failed. Logs: $($run.Stdout), $($run.Stderr)" -ForegroundColor Red }
    exit 1
}

$refreshOut = Join-Path $logRoot 'report_refresh.out.log'
$refreshErr = Join-Path $logRoot 'report_refresh.err.log'
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    & python cie/code/generate_cie_instances.py --action warm-start --profile ood --warm_start_time_limit 1 --memory_limit_mb $MemoryLimitMB > $refreshOut 2> $refreshErr
    $refreshExitCode = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previousPreference
}
if ($refreshExitCode -ne 0) { throw "OOD report refresh failed. Logs: $refreshOut, $refreshErr" }
Write-Host 'Completed: all nine OOD warm starts are compatible.' -ForegroundColor Green
