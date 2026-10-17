param(
    [ValidateSet('diagnostic','endpoints')][string]$Stage='diagnostic',
    [string]$Python='G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference='Stop'
$repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $repo
if ($Stage -eq 'endpoints') {
    & $Python .\JMS-version\joint_model\run_experiments.py run `
        --campaign .\JMS-version\results\joint_model\mode_endpoints_v1 `
        --time-limit 300 --stage2-limit 0 --initialization spbs `
        --initialization-budget 20 --memory-mb 24000 --resume
    if ($LASTEXITCODE -ne 0) {throw 'Endpoint campaign failed'}
} else {
    $cases=@(
        @{Name='n8_H3'; Source='minimal_joint_20260919_n8\runs\n8_H3_mixed_dual_s1_scip_fixed'},
        @{Name='n16_H3'; Source='minimal_joint_20260919_scale\runs\n16_H3_mixed_dual_s1_scip_joint'}
    )
    foreach ($case in $cases) {
        $source=Join-Path '.\JMS-version\results\joint_model' $case.Source
        $output=Join-Path '.\JMS-version\results\joint_model' ('bound_diagnostic_'+$case.Name+'_v1')
        & $Python .\JMS-version\joint_model\run_bound_diagnostic.py `
            --source $source --output $output --time-limit 120 --resume
        if ($LASTEXITCODE -ne 0) {throw "Diagnostic failed: $($case.Name)"}
    }
}
