param(
    [switch]$SkipGeneration,
    [switch]$SkipSolve,
    [switch]$IncludeUnchanged4x1,
    [switch]$OnlyWafer8Pure22,
    [double]$TimeLimit = 9000,
    [double]$StabilityTimeLimit = 3600,
    [int]$StabilityNodeLimit = -1,
    [int]$WarmStartTimeLimit = 1200,
    [double]$MemoryLimitMB = 4096,
    [int]$ScipVerbosity = 4,
    [ValidateSet('default', 'fast', 'aggressive', 'off')]
    [string]$ScipHeuristicsProfile = 'aggressive',
    [ValidateRange(0, 10)]
    [int]$ScipNonrootSeparationRounds = 0,
    [string]$RunLabel = 'jms_clean10_half2x2_splitbridge_physicalwait_rootonly_legacy50_20260827',
    [string]$Python = 'G:\conda\envs\a3cenv\python.exe',
    [string]$Checkpoint = 'data\mip_20260710\_mix_wafer18_20260710.lp_mix_wafer18\_mix_wafer18_20260710.lp_mix_wafer18_2026_07_10_10_19_40_0000--s-1\params.pkl'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if ($env:CONDA_DEFAULT_ENV -ne 'a3cenv') {
    throw 'Activate the required environment first: conda activate a3cenv'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "a3cenv Python is missing: $Python"
}
if (-not (Test-Path -LiteralPath $Checkpoint -PathType Leaf)) {
    throw "Frozen legacy checkpoint is missing: $Checkpoint"
}

$ExpectedCheckpointHash = '0895a8ad74c745591bc1bbc21bafa77b4df1d7b83c3a4f07494e35118005fdec'
$ActualCheckpointHash = (Get-FileHash -LiteralPath $Checkpoint -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualCheckpointHash -ne $ExpectedCheckpointHash) {
    throw "Frozen legacy checkpoint SHA-256 mismatch: $Checkpoint"
}

& $Python -c 'import torch,pyscipopt; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0), pyscipopt.__version__)'
if ($LASTEXITCODE -ne 0) {
    throw 'a3cenv/CUDA/PySCIPOpt preflight failed.'
}

$Cases = @(
    [pscustomobject]@{ Suite = 'wafer8_pure22_clean10'; Instance = 'wafer8_22_clean10_2x2half_20260827.lp'; N = 8; F = 0; M = 8 },
    [pscustomobject]@{ Suite = 'wafer8_pure41_clean10'; Instance = 'wafer8_41_clean10_2x2half_20260827.lp'; N = 8; F = 8; M = 0 },
    [pscustomobject]@{ Suite = 'wafer8_mixed11_clean10'; Instance = 'wafer8_mix_4_4_clean10_2x2half_20260827.lp'; N = 8; F = 4; M = 4 },
    [pscustomobject]@{ Suite = 'wafer16_pure22_clean10'; Instance = 'wafer16_22_clean10_2x2half_20260827.lp'; N = 16; F = 0; M = 16 },
    [pscustomobject]@{ Suite = 'wafer16_pure41_clean10'; Instance = 'wafer16_41_clean10_2x2half_20260827.lp'; N = 16; F = 16; M = 0 },
    [pscustomobject]@{ Suite = 'wafer16_mixed11_clean10'; Instance = 'wafer16_mix_8_8_clean10_2x2half_20260827.lp'; N = 16; F = 8; M = 8 }
)
if ($OnlyWafer8Pure22) {
    $Cases = @($Cases | Where-Object { $_.Suite -eq 'wafer8_pure22_clean10' })
} elseif (-not $IncludeUnchanged4x1) {
    $Cases = @($Cases | Where-Object { [int]$_.M -gt 0 })
}
$SuiteArgument = (@($Cases | ForEach-Object { $_.Suite }) -join ',')

$InstanceDir = 'generated_instances\jms_clean10_small_2x2half'
$ManifestPath = 'JMS\wafer8_16_clean10_half2x2_gantt_suites.json'
$ResultRoot = 'JMS\results\wafer_multiscale_gantt'
$RunDir = Join-Path $ResultRoot 'runs\wafer8_16_clean10'
$SolutionDir = Join-Path $ResultRoot 'solutions\wafer8_16_clean10'
$ValidationDir = Join-Path $ResultRoot 'validation\wafer8_16_clean10'
$GanttDir = Join-Path $ResultRoot 'gantt_2x2half_splitbridge_waitcompact_20260827'
$SafeRunLabel = [regex]::Replace($RunLabel, '[^A-Za-z0-9._-]', '_')
$CampaignRunDir = Join-Path $RunDir $SafeRunLabel
$CampaignSolutionDir = Join-Path $SolutionDir $SafeRunLabel
$CampaignValidationDir = Join-Path $ValidationDir $SafeRunLabel

New-Item -ItemType Directory -Force -Path $InstanceDir, $RunDir, $SolutionDir, $ValidationDir, $GanttDir, $CampaignRunDir, $CampaignSolutionDir, $CampaignValidationDir | Out-Null

$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
$ManifestSuites = @($Manifest.suites)

$ManifestNames = @($ManifestSuites | ForEach-Object { $_.name })
$MissingManifestSuites = @($Cases | Where-Object { $_.Suite -notin $ManifestNames })
if ($MissingManifestSuites.Count -gt 0) {
    throw "Manifest is missing suites: $($MissingManifestSuites.Suite -join ', ')"
}

function Invoke-InstanceGeneration {
    param([Parameter(Mandatory)]$Case)

    $WarmSeconds = if ([int]$Case.M -gt 0) { $WarmStartTimeLimit } else { 0 }
    $MixExposureSeconds = if ([int]$Case.M -gt 0) { 90 } else { 180 }
    $GeneratorArgs = @(
        '.\petri_mip_generator.py',
        "--output_dir=$InstanceDir",
        "--instance_name=$($Case.Instance)",
        "--warm_start_time_limit=$WarmSeconds",
        '--num_batches=15',
        '--num_pm=2',
        '--num_steps=13',
        "--total_wafers=$($Case.N)",
        "--mode_4x1_wafers=$($Case.F)",
        "--mode_2x2_wafers=$($Case.M)",
        '--pec_pool_size=8',
        '--batch_size=4',
        '--big_m=10000',
        '--pm_transfer_gap=1',
        '--pm_rotation_time_180=2',
        '--pair_transfer_time=4',
        '--atr_transfer_time=3',
        '--atr_return_time=3',
        '--atr_capacity=2',
        '--vtr_capacity=4',
        '--aligner_time=20',
        '--llupper_time=30',
        '--lllower_time=25',
        '--full_process_time=180',
        "--mix_boundary_process_time=$MixExposureSeconds",
        "--mix_internal_process_time=$MixExposureSeconds",
        '--cleaning_interval=10',
        '--cleaning_process_time=500',
        '--max_module_residency_time=10000',
        '--max_robot_residency_time=10000',
        '--max_schedule_wait_time=0',
        '--schedule_stability_objective=compact_resource_idle',
        '--process_mode=auto'
    )
    Write-Host "Generating $($Case.Instance): total=$($Case.N), 4x1=$($Case.F), 2x2=$($Case.M), 2x2 exposure=$MixExposureSeconds, clean=10"
    & $Python @GeneratorArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Generation/SPBS failed: $($Case.Instance)"
    }
}

if (-not $SkipGeneration) {
    foreach ($Case in $Cases) {
        Invoke-InstanceGeneration -Case $Case
    }
}

foreach ($Case in $Cases) {
    $LpPath = Join-Path $InstanceDir $Case.Instance
    if (-not (Test-Path -LiteralPath $LpPath -PathType Leaf)) {
        throw "Required LP is missing: $LpPath"
    }
    $ModelPath = Join-Path $InstanceDir (
        [IO.Path]::GetFileNameWithoutExtension([string]$Case.Instance) + '_model.md'
    )
    if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
        throw "Model description is missing: $ModelPath"
    }
    $ModelText = Get-Content -LiteralPath $ModelPath -Raw
    if ($ModelText -notmatch 'cleaning interval:\s*`10` full-chamber process cycles') {
        throw "Model description does not confirm cleaning_interval=10: $ModelPath"
    }
    if ($ModelText -notmatch '`4x1` process time:\s*`180\.0`') {
        throw "Model description does not confirm the 4x1 process time of 180 s: $ModelPath"
    }
    $Expected2x2Exposure = if ([int]$Case.M -gt 0) { '90.0' } else { '180.0' }
    $Expected2x2Pattern = '`2x2` process time for each first/second exposure:\s*`' + [regex]::Escape($Expected2x2Exposure) + '`'
    if ($ModelText -notmatch $Expected2x2Pattern) {
        throw "Model description does not confirm the expected 2x2 exposure time of $Expected2x2Exposure s: $ModelPath"
    }
    if ([int]$Case.M -gt 0 -and $ModelText -notmatch 'bridge may use one four-gripper.*otherwise it splits') {
        throw "Model description does not confirm optional combined/split 2x2 bridges: $ModelPath"
    }
}

$InstanceHashes = foreach ($Case in $Cases) {
    Get-FileHash -LiteralPath (Join-Path $InstanceDir $Case.Instance) -Algorithm SHA256
}
$InstanceHashes | Export-Csv -LiteralPath (Join-Path $CampaignRunDir 'instance_sha256.csv') -NoTypeInformation
Get-FileHash -LiteralPath $Checkpoint -Algorithm SHA256 |
    Export-Csv -LiteralPath (Join-Path $CampaignRunDir 'checkpoint_sha256.csv') -NoTypeInformation

$TimeLimitText = $TimeLimit.ToString([Globalization.CultureInfo]::InvariantCulture)
$MemoryLimitText = $MemoryLimitMB.ToString([Globalization.CultureInfo]::InvariantCulture)
$StabilityTimeLimitText = $StabilityTimeLimit.ToString([Globalization.CultureInfo]::InvariantCulture)

if (-not $SkipSolve) {
    $RunnerArgs = @(
        '-u',
        '.\cie\code\run_cie_benchmarks.py',
        "--manifest=$ManifestPath",
        "--output_dir=$CampaignRunDir",
        "--solution_dir=$CampaignSolutionDir",
        '--methods=proposed',
        '--splits=jms_clean10_small_half2x2_gantt',
        "--suites=$SuiteArgument",
        '--seeds=1',
        '--training_seed=1',
        "--run_label=$RunLabel",
        "--time_limit=$TimeLimitText",
        '--stability_profile=full',
        "--lexicographic_stability_time_limit=$StabilityTimeLimitText",
        "--lexicographic_stability_node_limit=$StabilityNodeLimit",
        '--lexicographic_free_schedule_order_decisions',
        '--schedule_linear_physical_route_only',
        '--schedule_linear_wait_weight=1',
        '--schedule_linear_max_wait_weight=10',
        '--schedule_cadence_deviation_weight=0',
        '--device=cuda:0',
        "--memory_limit_mb=$MemoryLimitText",
        '--warm_start=auto',
        '--reuse_existing_solution_as_warm_start',
        '--scip_emphasis=optimality',
        "--scip_heuristics_profile=$ScipHeuristicsProfile",
        "--scip_nonroot_separation_rounds=$ScipNonrootSeparationRounds",
        "--scip_verbosity=$ScipVerbosity",
        '--sel_cuts_percent=0.2',
        '--policy_type=with_token',
        '--cutsel_max_candidates=128',
        '--cutsel_max_selected_cuts=30',
        '--structure_pool_factor=2.0',
        '--structure_anchor_ratio=0.25',
        '--structure_quality_weight=0.35',
        '--structure_policy_weight=0.20',
        '--structure_coverage_weight=0.25',
        '--structure_representation_weight=0.20',
        '--proposed_config=.\cie\configs\cie_proposed_inference.json',
        "--proposed_model=$Checkpoint",
        '--fail_on_empty_suite'
    )
    $SolveLog = Join-Path $CampaignRunDir 'solve.log'
    $PreviousErrorActionPreference = $ErrorActionPreference
    $SolveExitCode = -1
    try {
        $ErrorActionPreference = 'Continue'
        & $Python @RunnerArgs 2>&1 |
            ForEach-Object {
                if ($_ -is [Management.Automation.ErrorRecord]) {
                    $_.Exception.Message
                }
                else {
                    $_
                }
            } |
            Tee-Object -FilePath $SolveLog
        $SolveExitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
    }
    if ($SolveExitCode -ne 0) {
        throw "8/16-wafer clean10 Proposed solve failed. Full log: $SolveLog"
    }
}

$AnalyzeArgs = @(
    '.\cie\code\analyze_cie_solutions.py',
    "--input_dir=$CampaignRunDir",
    "--output_dir=$CampaignValidationDir",
    '--validate',
    '--fail_on_invalid'
)
& $Python @AnalyzeArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Independent SCIP validation failed for the clean10 8/16-wafer campaign.'
}

$MetricsPath = Join-Path $CampaignValidationDir 'cie_manufacturing_metrics.json'
$Metrics = Get-Content -LiteralPath $MetricsPath -Raw | ConvertFrom-Json
$Rows = @($Metrics.rows | Where-Object {
    $_.run_label -eq $RunLabel
})
if ($Rows.Count -ne $Cases.Count) {
    throw "Expected $($Cases.Count) clean10 result rows for run label $RunLabel, found $($Rows.Count)."
}
$RejectedRows = @($Rows | Where-Object {
    $_.physically_feasible -ne $true -or
    $_.schedule_linear_physical_route_only -ne $true -or
    $_.lexicographic_free_schedule_order_decisions -ne $true -or
    [string]$_.status -ne 'optimal' -or
    [double]$_.gap -gt 1e-8 -or
    [string]$_.stability_status -ne 'optimal' -or
    $null -eq $_.stability_gap -or
    [double]$_.stability_gap -gt 1e-8
})
if ($RejectedRows.Count -gt 0) {
    $FailureSummary = @($RejectedRows | ForEach-Object {
        "$($_.suite)(primary=$($_.status), primary_gap=$($_.gap), stability=$($_.stability_status), stability_gap=$($_.stability_gap), physical=$($_.physically_feasible), physical_wait_objective=$($_.schedule_linear_physical_route_only), free_schedule_choices=$($_.lexicographic_free_schedule_order_decisions), cmax=$($_.cmax), total_wait=$($_.physical_route_total_wait), max_wait=$($_.physical_route_max_wait))"
    }) -join '; '
    throw "Publication Gantt export requires the exact physical-wait protocol, primary/wait-compaction optimality, both gaps<=1e-8, and independent physical feasibility: $FailureSummary"
}

foreach ($Row in $Rows) {
    $Stem = [IO.Path]::GetFileNameWithoutExtension([string]$Row.instance)
    $InstanceGanttDir = Join-Path $GanttDir $Stem
    $JsonPath = Join-Path $InstanceGanttDir ($Stem + '_validated_solutions.json')
    if ([string]::IsNullOrWhiteSpace([string]$Row.path)) {
        throw "Missing instance path in validation row: $Stem"
    }
    if ([string]::IsNullOrWhiteSpace([string]$Row.solution_file)) {
        throw "Missing solution path in validation row: $Stem"
    }
    $ExportArgs = @(
        '.\cie\code\export_cie_gantt_json.py',
        "--instance=$($Row.path)",
        "--solution=$($Row.solution_file)",
        "--output_json=$JsonPath",
        "--solver_status=$($Row.status)",
        "--solver_gap=$($Row.gap)",
        "--run_label=$RunLabel"
    )
    & $Python @ExportArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Gantt JSON export failed: $Stem"
    }
    $GanttArgs = @(
        '.\petri_gantt.py',
        "--solution_json=$JsonPath",
        "--output_dir=$InstanceGanttDir",
        '--view=all'
    )
    & $Python @GanttArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Gantt rendering failed: $Stem"
    }
}

& $Python -m pytest .\tests\test_petri_gantt_paths.py .\RL-SAT\tests\test_compatible_petri_gantt.py -q
if ($LASTEXITCODE -ne 0) {
    throw 'Gantt regression tests failed.'
}

$ValidatedSuites = ($Cases | ForEach-Object { $_.Suite }) -join ', '
Write-Host "Validated clean10 Gantt evidence for $($Cases.Count) selected case(s) [$ValidatedSuites]: $(Join-Path $ProjectRoot $GanttDir)"

