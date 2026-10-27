# Run one campaign in this foreground terminal. No shell function setup needed.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('core','smoke','crossover','ablation','sensitivity','scale','doe','ood')]
    [string]$Suite,
    [Parameter(Mandatory=$true)][string]$Output,
    [ValidateRange(1,1000000)][int]$MemoryMb = 6000,
    [ValidateRange(1,64)][int]$Jobs = 2,
    [ValidateSet('standard','root_only')][string]$CutProfile = 'standard',
    [ValidateRange(1,86400)][int]$TimeLimit = 300,
    [ValidateRange(1,86400)][int]$WallLimit = 1800,
    [int[]]$Seeds = @(1,2,3),
    [ValidateRange(1,1000)][int]$TrainingSeed = 1,
    [ValidateRange(0,86400)][int]$SpbsBudget = 20,
    [ValidateRange(0,1000000)][int]$ReserveMb = 2048,
    [string]$Python = 'python',
    [switch]$RetryFailed,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
$workspaceRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
Push-Location -LiteralPath $workspaceRoot
try {
    $campaignPath = if ([IO.Path]::IsPathRooted($Output)) {
        [IO.Path]::GetFullPath($Output)
    } else {
        [IO.Path]::GetFullPath((Join-Path $workspaceRoot $Output))
    }
    if (-not $campaignPath.StartsWith($workspaceRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Output must be a directory inside this workspace.'
    }
    $manifest = Join-Path $campaignPath 'campaign.json'
    if (Test-Path -LiteralPath $campaignPath) {
        if (-not (Test-Path -LiteralPath $manifest)) {
            throw 'Existing directory has no campaign.json. Inspect it without deleting results.'
        }
        $spec = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifest | ConvertFrom-Json
        if ($spec.suite -ne $Suite -or $spec.memory_mb -ne $MemoryMb -or
            $spec.time_limit -ne $TimeLimit -or $spec.wall_limit -ne $WallLimit -or
            $spec.cut_profile -ne $CutProfile -or $spec.training_seed -ne $TrainingSeed -or
            $spec.spbs_budget -ne $SpbsBudget -or ($spec.seeds -join ',') -ne ($Seeds -join ',')) {
            throw 'Frozen campaign settings differ. Use a new output directory; do not overwrite.'
        }
    }
    & $Python -c 'import sys, psutil, pyscipopt, torch; print(sys.executable)'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed. Install missing packages in the selected Python environment.' }
    Write-Host 'Dependencies OK'
    Write-Host "Campaign: $campaignPath"
    Write-Host "Suite=$Suite MemoryMB=$MemoryMb Jobs=$Jobs GPU-slots=1 ReserveMB=$ReserveMb"
    if ($CheckOnly) {
        Write-Host 'Preflight complete. No campaign prepared and no experiment launched.'
        return
    }
    if (-not (Test-Path -LiteralPath $campaignPath)) {
        & $Python JMS-version/joint_model/revalidate.py prepare --suite $Suite --output $campaignPath --time-limit $TimeLimit --seeds $Seeds --training-seed $TrainingSeed --spbs-budget $SpbsBudget --cut-profile $CutProfile --memory-mb $MemoryMb --wall-limit $WallLimit
        if ($LASTEXITCODE -ne 0) { throw 'Prepare failed. Inspect the error; no run was launched.' }
    }
    $retryArguments = @()
    if ($RetryFailed) { $retryArguments = @('--retry-failed') }
    & $Python -u JMS-version/tools/experiment_console.py run --campaign $campaignPath --jobs $Jobs --gpu-slots 1 --reserve-mb $ReserveMb @retryArguments
    if ($LASTEXITCODE -ne 0) { throw 'Run stopped. Inspect the error before continuing.' }
    $finishedPath = Join-Path $campaignPath 'finished.json'
    if (-not (Test-Path -LiteralPath $finishedPath)) { throw 'No completion record. Inspect progress before continuing.' }
    $report = Get-Content -Raw -Encoding UTF8 -LiteralPath $finishedPath | ConvertFrom-Json
    $report | Format-List
    if (-not $report.all_cells_successful) {
        $failedCount = [int]$report.states.execution_failed
        $pendingCount = [int]$report.states.pending
        $cellsPath = Join-Path $campaignPath 'summary/cells.csv'
        $failedRows = @()
        if (Test-Path -LiteralPath $cellsPath) {
            $failedRows = @(Import-Csv -LiteralPath $cellsPath -Encoding UTF8 |
                Where-Object { $_.state -in @('execution_failed','pending') })
            $failedRows | Select-Object id,state,reason | Format-Table -AutoSize -Wrap | Out-Host
        }
        Write-Host "Coverage: $(Join-Path $campaignPath 'summary/coverage.json')"
        Write-Host "Worker logs: $(Join-Path $campaignPath 'logs')"
        if (@($failedRows | Where-Object { $_.reason -eq 'process_memory_guard' }).Count -gt 0) {
            throw "Queue ended: failed=$failedCount pending=$pendingCount. Process memory guard triggered. Do not retry unchanged or increase only the solve time; inspect model memory use before larger campaigns."
        }
        throw "Queue ended: failed=$failedCount pending=$pendingCount. Inspect the listed cells and worker logs before retrying or continuing."
    }
    Write-Host 'Queue complete. Review feasibility, bounds and evidence before starting the next campaign.'
}
finally {
    Pop-Location
}
