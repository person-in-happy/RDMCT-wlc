param(
    [int]$WaitForProcessId = 0,
    [double]$TimeLimit = 28800
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if ($WaitForProcessId -gt 0) {
    $Existing = Get-Process -Id $WaitForProcessId -ErrorAction SilentlyContinue
    if ($null -ne $Existing) {
        Write-Host "Waiting for existing experiment PID $WaitForProcessId to finish without interruption."
        Wait-Process -Id $WaitForProcessId
    }
}

$Python = 'G:\conda\envs\a3cenv\python.exe'
$Campaign = 'JMS\results\mode_cleaning_crossover\jms_mode_cleaning_discovery_n16_n17_n20_20260831'
$RunDir = Join-Path $Campaign 'runs_retry_no_incumbent_old_cmax_20260904'
$SolutionDir = Join-Path $Campaign 'solutions_retry_no_incumbent_old_cmax_20260904'
New-Item -ItemType Directory -Force -Path $RunDir, $SolutionDir | Out-Null

$CheckpointRows = @(Import-Csv -LiteralPath 'cie\results\repro_manifest\selected_checkpoint_manifest.csv' |
    Where-Object { $_.family -eq 'proposed' -and [int]$_.training_seed -eq 1 })
if ($CheckpointRows.Count -ne 1) {
    throw 'Expected exactly one frozen Proposed checkpoint for training seed 1.'
}
$Checkpoint = [string]$CheckpointRows[0].checkpoint

$Suites = @(
    'mode_n016_clean02_pure22'
    'mode_n017_clean02_pure22'
    'mode_n020_clean02_pure22'
    'mode_n020_clean02_mixed11'
) -join ','

$Args = @(
    '-u'
    '.\cie\code\run_cie_benchmarks.py'
    '--manifest=JMS\generated_manifests\jms_mode_cleaning_discovery_n16_n17_n20_20260831.json'
    "--output_dir=$RunDir"
    "--solution_dir=$SolutionDir"
    '--methods=proposed'
    '--splits=mode_cleaning_crossover'
    "--suites=$Suites"
    '--seeds=1'
    '--training_seed=1'
    '--run_label=jms_mode_cleaning_noincumbent_retry_old_cmax_20260904_trainseed_1'
    "--time_limit=$($TimeLimit.ToString([Globalization.CultureInfo]::InvariantCulture))"
    '--stability_profile=stage2_off'
    '--device=cuda:0'
    '--memory_limit_mb=4096'
    '--warm_start=auto'
    '--reuse_existing_solution_as_warm_start'
    '--scip_emphasis=optimality'
    '--scip_heuristics_profile=aggressive'
    '--scip_nonroot_separation_rounds=0'
    '--scip_verbosity=2'
    '--sel_cuts_percent=0.2'
    '--decode_type=beam_search'
    '--policy_type=with_token'
    '--cutsel_max_candidates=128'
    '--cutsel_max_selected_cuts=16'
    '--structure_pool_factor=2.0'
    '--structure_anchor_ratio=0.25'
    '--structure_quality_weight=0.35'
    '--structure_policy_weight=0.20'
    '--structure_coverage_weight=0.25'
    '--structure_representation_weight=0.20'
    '--proposed_config=cie\configs\cie_proposed_inference.json'
    "--proposed_model=$Checkpoint"
    '--fail_on_empty_suite'
)

$Log = Join-Path $RunDir 'solve.log'
$PreviousErrorActionPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & $Python @Args 2>&1 | ForEach-Object {
        if ($_ -is [Management.Automation.ErrorRecord]) {
            $_.Exception.Message
        }
        else {
            $_
        }
    } | Tee-Object -FilePath $Log -Append
    $ExitCode = $LASTEXITCODE
}
finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
}

if ($ExitCode -ne 0) {
    throw "Retry campaign failed with exit code $ExitCode. See $Log"
}
