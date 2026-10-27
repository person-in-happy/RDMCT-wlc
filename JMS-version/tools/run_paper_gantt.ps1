# Independent full-model optimality attempt. Never re-label a timeout as optimal.
[CmdletBinding()]
param(
    [string]$Python = 'G:\conda\envs\a3cenv\python.exe',
    [string]$Output = 'JMS-version/results/paper_gantt_n16_optimal_attempt_20261020',
    [string]$Figures = 'JMS-version/figures/paper_gantt_n16_certified_20261020',
    [ValidateRange(1,86400)][int]$TimeLimit = 7200,
    [ValidateRange(1,86400)][int]$WallLimit = 10800,
    [ValidateRange(0,86400)][int]$SpbsBudget = 300,
    [ValidateRange(1,1000000)][int]$MemoryMb = 14000,
    [switch]$CheckOnly,
    [switch]$RenderOnly
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
Push-Location -LiteralPath $repoRoot
try {
    if ($CheckOnly -and $RenderOnly) { throw 'Choose CheckOnly or RenderOnly.' }
    if ($WallLimit -le ($TimeLimit + $SpbsBudget)) {
        throw 'WallLimit must leave time for reference construction and model export.'
    }
    $campaignPath = [IO.Path]::GetFullPath((Join-Path $repoRoot $Output))
    $figurePath = [IO.Path]::GetFullPath((Join-Path $repoRoot $Figures))
    $resultRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'JMS-version/results/'))
    $figureRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot 'JMS-version/figures/'))
    if (-not $campaignPath.StartsWith($resultRoot, [StringComparison]::OrdinalIgnoreCase) -or
        -not $figurePath.StartsWith($figureRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Use isolated subdirectories of JMS-version/results and JMS-version/figures.'
    }
    $cases = @('n16_H3_4x1_dual', 'n16_H3_2x2_dual', 'n16_H10_4x1_dual', 'n16_H10_2x2_dual')
    $manifestPath = Join-Path $campaignPath 'campaign.json'
    if (Test-Path -LiteralPath $campaignPath) {
        if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Existing directory lacks campaign.json; inspect it without deleting results.' }
        $spec = Get-Content -Raw -Encoding UTF8 -LiteralPath $manifestPath | ConvertFrom-Json
        $expected = @($cases | ForEach-Object { "${_}__s1__joint" } | Sort-Object)
        $actual = @($spec.cells | ForEach-Object { $_.id } | Sort-Object)
        if (($expected -join '|') -ne ($actual -join '|')) { throw 'Existing campaign is not the four selected full-model cases.' }
    }
    $batchArgs = @{
        Suite = 'crossover'; Output = $campaignPath; Python = $Python
        TimeLimit = $TimeLimit; WallLimit = $WallLimit; SpbsBudget = $SpbsBudget
        MemoryMb = $MemoryMb; Jobs = 1; Seeds = @(1); CutProfile = 'standard'
    }
    if ($CheckOnly) {
        & "$PSScriptRoot/run_validation_batch.ps1" @batchArgs -CheckOnly
        & $Python -c 'import matplotlib; print(matplotlib.__version__)'
        if ($LASTEXITCODE -ne 0) { throw 'Matplotlib dependency check failed.' }
        Write-Host 'Four cases, fixed seed 1, full candidate space. No solve or preparation performed.'
        return
    }
    if (-not $RenderOnly) {
        $otherRuns = @(Get-CimInstance Win32_Process | Where-Object {
            $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and
            $_.CommandLine -match 'experiment_console\.py.+\brun\b|revalidate\.py.+\b(run|worker)\b'
        })
        if ($otherRuns.Count -gt 0) {
            $otherRuns | Select-Object ProcessId, CommandLine | Format-List | Out-Host
            throw 'Another validation queue is active. Let it finish before this 14 GB run.'
        }
        if (-not (Test-Path -LiteralPath $manifestPath)) {
            & $Python JMS-version/joint_model/revalidate.py prepare --suite crossover --cases $cases --output $campaignPath --time-limit $TimeLimit --seeds 1 --training-seed 1 --spbs-budget $SpbsBudget --cut-profile standard --memory-mb $MemoryMb --wall-limit $WallLimit
            if ($LASTEXITCODE -ne 0) { throw 'Preparation failed.' }
        }
        Write-Host 'Attempting full-model Cmax optimality. Time limits do not guarantee proof.'
        & "$PSScriptRoot/run_validation_batch.ps1" @batchArgs
    }
    & $Python -X utf8 JMS-version/tools/render_optional_cleaning_gantt.py --campaign $campaignPath --seed 1 --output $figurePath --require-optimal --wafer-flow
    if ($LASTEXITCODE -ne 0) {
        throw 'No certified paper figures produced: inspect primary bounds, validation and logs. Do not retry unchanged timeouts expecting continuation.'
    }
    Write-Host "Certified Cmax figures and continuous wafer timelines: $figurePath"
}
finally {
    Pop-Location
}
