param(
    [ValidateSet('core','algorithm')][string]$Stage='core',
    [string]$Tag='minimal_joint_20260919',
    [switch]$PrepareOnly,
    [string]$Python='G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $repo
$runner=Join-Path $PSScriptRoot 'run_experiments.py'
& $Python (Join-Path $repo 'JMS-version\tools\check_joint_experiment_readiness.py') --require-full
if ($LASTEXITCODE -ne 0) {throw 'Joint-model execution readiness failed'}
function Run-Group([string]$Suffix,[string[]]$Extra) {
    $campaign=Join-Path $repo "JMS-version\results\joint_model\${Tag}_${Suffix}"
    if (-not (Test-Path -LiteralPath (Join-Path $campaign 'campaign.json'))) {
        & $Python $runner prepare --suite comparison --output $campaign --thresholds 3 --recipes mixed @Extra
        if ($LASTEXITCODE -ne 0) {throw "Prepare failed: $Suffix"}
    }
    if ($PrepareOnly) { return }
    & $Python $runner run --campaign $campaign --time-limit 300 --stage2-limit 0 --initialization spbs --initialization-budget 20 --memory-mb 24000 --resume
    if ($LASTEXITCODE -ne 0) {throw "Run failed: $Suffix"}
}
if ($Stage -eq 'core') {
    Run-Group 'odd_sources' @('--sizes','6','--sources','single','dual','--seeds','1','--methods','scip','--formulations','joint','fixed')
    Run-Group 'n8' @('--sizes','8','--sources','dual','--seeds','1','--methods','scip','--formulations','joint','fixed')
    Run-Group 'scale' @('--sizes','16','24','--sources','dual','--seeds','1','--methods','scip','--formulations','joint')
} else {
    $baseline=Join-Path $repo "JMS-version\results\joint_model\${Tag}_n8\runs\n8_H3_mixed_dual_s1_scip_joint\result.json"
    if (-not (Test-Path -LiteralPath $baseline)) {throw 'Run core first: the SCIP seed-1 baseline is reused, not rerun.'}
    Run-Group 'selectors' @('--sizes','8','--sources','dual','--seeds','1','2','3','--methods','hem','proposed','--formulations','joint')
    Run-Group 'scip_extra_seeds' @('--sizes','8','--sources','dual','--seeds','2','3','--methods','scip','--formulations','joint')
}
