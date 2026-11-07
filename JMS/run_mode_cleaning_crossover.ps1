param(
    [switch]$SkipGeneration,
    [switch]$SkipSolve,
    [switch]$GenerateOnly,
    [string]$WaferCounts = '16,17,20',
    [string]$InstanceRelativeDir = 'generated_instances\jms_mode_cleaning_crossover_equal_total180',
    [string]$CleaningIntervals = '2-10',
    [string]$TrainingSeeds = '1',
    [string]$SolverSeeds = '1',
    [double]$TimeLimit = 7200,
    [int]$WarmStartTimeLimit = 300,
    [double]$MemoryLimitMB = 4096,
    [int]$ScipVerbosity = 2,
    [ValidateSet('default', 'fast', 'aggressive', 'off')]
    [string]$ScipHeuristicsProfile = 'aggressive',
    [ValidateRange(0, 10)]
    [int]$ScipNonrootSeparationRounds = 0,
    [string]$RunLabel = 'jms_mode_cleaning_crossover_equal_total180_20260831',
    [string]$Python = 'G:\conda\envs\a3cenv\python.exe',
    [string]$CheckpointManifest = 'cie\results\repro_manifest\selected_checkpoint_manifest.csv',
    [string]$ProposedConfig = 'cie\configs\cie_proposed_inference.json'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

function ConvertTo-IntegerList {
    param(
        [Parameter(Mandatory)][string]$Spec,
        [Parameter(Mandatory)][int]$Minimum,
        [Parameter(Mandatory)][string]$Name
    )
    $Values = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($RawToken in $Spec.Split(',')) {
        $Token = $RawToken.Trim()
        if ([string]::IsNullOrWhiteSpace($Token)) {
            continue
        }
        if ($Token -match '^(\d+)\s*-\s*(\d+)$') {
            $First = [int]$Matches[1]
            $Last = [int]$Matches[2]
            if ($Last -lt $First) {
                throw "$Name contains a descending range: $Token"
            }
            foreach ($Value in $First..$Last) {
                [void]$Values.Add($Value)
            }
        }
        elseif ($Token -match '^\d+$') {
            [void]$Values.Add([int]$Token)
        }
        else {
            throw "$Name contains an invalid integer/range: $Token"
        }
    }
    $Result = @($Values | Sort-Object)
    if ($Result.Count -eq 0 -or [int]$Result[0] -lt $Minimum) {
        throw "$Name must contain integers greater than or equal to $Minimum. Received: $Spec"
    }
    return $Result
}

if ($env:CONDA_DEFAULT_ENV -ne 'a3cenv') {
    throw 'Activate the required environment first: conda activate a3cenv'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "a3cenv Python is missing: $Python"
}
if (-not (Test-Path -LiteralPath $CheckpointManifest -PathType Leaf)) {
    throw "Frozen checkpoint manifest is missing: $CheckpointManifest"
}
if (-not (Test-Path -LiteralPath $ProposedConfig -PathType Leaf)) {
    throw "Proposed inference config is missing: $ProposedConfig"
}

$WaferList = @(ConvertTo-IntegerList -Spec $WaferCounts -Minimum 1 -Name 'WaferCounts')
$CleaningList = @(ConvertTo-IntegerList -Spec $CleaningIntervals -Minimum 2 -Name 'CleaningIntervals')
$TrainingSeedList = @(ConvertTo-IntegerList -Spec $TrainingSeeds -Minimum 1 -Name 'TrainingSeeds')
$SolverSeedList = @(ConvertTo-IntegerList -Spec $SolverSeeds -Minimum 1 -Name 'SolverSeeds')

if ($TimeLimit -le 0) {
    throw 'TimeLimit must be positive.'
}
if ($WarmStartTimeLimit -lt 0) {
    throw 'WarmStartTimeLimit cannot be negative.'
}

& $Python -c 'import torch,pyscipopt; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0), pyscipopt.__version__)'
if ($LASTEXITCODE -ne 0) {
    throw 'a3cenv/CUDA/PySCIPOpt preflight failed.'
}

$SafeRunLabel = [regex]::Replace($RunLabel, '[^A-Za-z0-9._-]', '_')
$ManifestRelativeDir = 'JMS\generated_manifests'
$ManifestPath = Join-Path $ManifestRelativeDir ("$SafeRunLabel.json")
$CampaignRoot = Join-Path 'JMS\results\mode_cleaning_crossover' $SafeRunLabel
$CampaignRunDir = Join-Path $CampaignRoot 'runs'
$CampaignSolutionDir = Join-Path $CampaignRoot 'solutions'
$CampaignValidationDir = Join-Path $CampaignRoot 'validation'
$CampaignSummaryDir = Join-Path $CampaignRoot 'summary'

New-Item -ItemType Directory -Force -Path `
    $InstanceRelativeDir, $ManifestRelativeDir, $CampaignRunDir, `
    $CampaignSolutionDir, $CampaignValidationDir, $CampaignSummaryDir | Out-Null

$Cases = @()
foreach ($N in $WaferList) {
    foreach ($CleaningInterval in $CleaningList) {
        foreach ($Mode in @('pure41', 'pure22', 'mixed11')) {
            $Suite = 'mode_n{0:d3}_clean{1:d2}_{2}' -f $N, $CleaningInterval, $Mode
            $Instance = '{0}_equal_total180_20260831.lp' -f $Suite
            if ($Mode -eq 'pure41') {
                $Mode41Wafers = $N
                $Mode22Wafers = 0
            }
            elseif ($Mode -eq 'pure22') {
                $Mode41Wafers = 0
                $Mode22Wafers = $N
            }
            else {
                # For odd N, the 4x1 population receives the one extra product wafer.
                $Mode41Wafers = [int][Math]::Ceiling($N / 2.0)
                $Mode22Wafers = [int][Math]::Floor($N / 2.0)
            }
            $Cases += [pscustomobject]@{
                Suite = $Suite
                Instance = $Instance
                N = $N
                CleaningInterval = $CleaningInterval
                Mode = $Mode
                F = $Mode41Wafers
                M = $Mode22Wafers
                NumBatches = [Math]::Max(15, [int][Math]::Ceiling($N / 2.0) + 2)
            }
        }
    }
}

function Invoke-InstanceGeneration {
    param([Parameter(Mandatory)]$Case)

    $WarmSeconds = if ([int]$Case.M -gt 0) { $WarmStartTimeLimit } else { 0 }
    $GeneratorArgs = @(
        '.\petri_mip_generator.py',
        "--output_dir=$InstanceRelativeDir",
        "--instance_name=$($Case.Instance)",
        "--warm_start_time_limit=$WarmSeconds",
        '--allow_missing_warm_start',
        "--num_batches=$($Case.NumBatches)",
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
        '--mix_boundary_process_time=90',
        '--mix_internal_process_time=90',
        "--cleaning_interval=$($Case.CleaningInterval)",
        '--cleaning_process_time=500',
        '--max_module_residency_time=10000',
        '--max_robot_residency_time=10000',
        '--max_schedule_wait_time=0',
        '--schedule_stability_objective=compact_resource_idle',
        '--process_mode=auto'
    )
    Write-Host (
        'Generating {0}: wafers={1}, mode={2}, clean={3}, 4x1=180 s, 2x2=90+90 s, combined bridge=4 s' -f `
        $Case.Instance, $Case.N, $Case.Mode, $Case.CleaningInterval
    )
    & $Python @GeneratorArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Generation failed: $($Case.Instance)"
    }
}

if (-not $SkipGeneration) {
    foreach ($Case in $Cases) {
        Invoke-InstanceGeneration -Case $Case
    }
}

foreach ($Case in $Cases) {
    $LpPath = Join-Path $InstanceRelativeDir $Case.Instance
    $ModelPath = Join-Path $InstanceRelativeDir (
        [IO.Path]::GetFileNameWithoutExtension([string]$Case.Instance) + '_model.md'
    )
    if (-not (Test-Path -LiteralPath $LpPath -PathType Leaf)) {
        throw "Required LP is missing: $LpPath"
    }
    if (-not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
        throw "Model description is missing: $ModelPath"
    }
    $ModelText = Get-Content -LiteralPath $ModelPath -Raw
    $CleanPattern = 'cleaning interval:\s*`' + [regex]::Escape([string]$Case.CleaningInterval) + '` full-chamber process cycles'
    if ($ModelText -notmatch $CleanPattern) {
        throw "Model description has the wrong cleaning interval: $ModelPath"
    }
    if ($ModelText -notmatch '`4x1` process time:\s*`180\.0`') {
        throw "Model description does not confirm 4x1=180 s: $ModelPath"
    }
    if ($ModelText -notmatch '`2x2` process time for each first/second exposure:\s*`90\.0`') {
        throw "Model description does not confirm 2x2=90+90 s: $ModelPath"
    }
    if ($ModelText -notmatch 'intermediate `2x2` bridge may use one four-gripper') {
        throw "Model description does not confirm the combined 2x2 exchange: $ModelPath"
    }
    if ($ModelText -notmatch 'Every loaded VTR action has exact duration `4\.0`') {
        throw "Model description does not confirm the 4 s VTR action: $ModelPath"
    }
    if ($ModelText -notmatch 'c_max`: end-to-end product makespan, ending when the last product wafer returns to an LP; post-production terminal cleaning is excluded') {
        throw "Model description does not confirm the product-return Cmax cutoff: $ModelPath"
    }
}

$ManifestSuites = foreach ($Case in $Cases) {
    [ordered]@{
        name = $Case.Suite
        family = 'dual_source_cluster_tool'
        scale = ('n{0:d3}_clean{1:d2}_equal_total180' -f $Case.N, $Case.CleaningInterval)
        split = 'mode_cleaning_crossover'
        root = ('../../{0}/{1}' -f ($InstanceRelativeDir -replace '\\', '/'), $Case.Instance)
    }
}
$ManifestPayload = [ordered]@{
    description = 'JMS supplement: pure 4x1, pure 2x2, and 1:1 mixed modes with 4x1=180 s and 2x2=90+90 s across cleaning intervals.'
    suites = @($ManifestSuites)
}
$ManifestJson = $ManifestPayload | ConvertTo-Json -Depth 6
$ManifestFullPath = Join-Path $ProjectRoot $ManifestPath
$WriteManifest = -not (Test-Path -LiteralPath $ManifestFullPath -PathType Leaf)
if (-not $WriteManifest) {
    $ExistingManifestJson = [IO.File]::ReadAllText($ManifestFullPath)
    $WriteManifest = $ExistingManifestJson -cne $ManifestJson
}
if ($WriteManifest) {
    [IO.File]::WriteAllText(
        $ManifestFullPath,
        $ManifestJson,
        (New-Object Text.UTF8Encoding($false))
    )
}

$InstanceHashes = foreach ($Case in $Cases) {
    Get-FileHash -LiteralPath (Join-Path $InstanceRelativeDir $Case.Instance) -Algorithm SHA256
}
$InstanceHashes | Export-Csv -LiteralPath (Join-Path $CampaignRoot 'instance_sha256.csv') -NoTypeInformation
Get-FileHash -LiteralPath $ManifestPath -Algorithm SHA256 |
    Export-Csv -LiteralPath (Join-Path $CampaignRoot 'manifest_sha256.csv') -NoTypeInformation
Get-FileHash -LiteralPath $ProposedConfig -Algorithm SHA256 |
    Export-Csv -LiteralPath (Join-Path $CampaignRoot 'proposed_config_sha256.csv') -NoTypeInformation

$CheckpointRows = @(Import-Csv -LiteralPath $CheckpointManifest)
$SelectedCheckpoints = @()
foreach ($TrainingSeed in $TrainingSeedList) {
    $Matches = @($CheckpointRows | Where-Object {
        $_.family -eq 'proposed' -and [int]$_.training_seed -eq $TrainingSeed
    })
    if ($Matches.Count -ne 1) {
        throw "Expected exactly one frozen Proposed checkpoint for training seed $TrainingSeed."
    }
    $Checkpoint = [string]$Matches[0].checkpoint
    if (-not (Test-Path -LiteralPath $Checkpoint -PathType Leaf)) {
        throw "Frozen Proposed checkpoint is missing: $Checkpoint"
    }
    $ActualHash = (Get-FileHash -LiteralPath $Checkpoint -Algorithm SHA256).Hash.ToLowerInvariant()
    $ExpectedHash = ([string]$Matches[0].checkpoint_sha256).ToLowerInvariant()
    if ($ActualHash -ne $ExpectedHash) {
        throw "Frozen Proposed checkpoint SHA-256 mismatch: $Checkpoint"
    }
    $SelectedCheckpoints += [pscustomobject]@{
        TrainingSeed = $TrainingSeed
        Checkpoint = $Checkpoint
        SHA256 = $ActualHash
    }
}
$SelectedCheckpoints | Export-Csv -LiteralPath (Join-Path $CampaignRoot 'checkpoint_sha256.csv') -NoTypeInformation

if ($GenerateOnly) {
    Write-Host "Generation audit completed for $($Cases.Count) instance(s). Manifest: $(Join-Path $ProjectRoot $ManifestPath)"
    exit 0
}

$TimeLimitText = $TimeLimit.ToString([Globalization.CultureInfo]::InvariantCulture)
$MemoryLimitText = $MemoryLimitMB.ToString([Globalization.CultureInfo]::InvariantCulture)
$SolverSeedArgument = $SolverSeedList -join ','

if (-not $SkipSolve) {
    $SolveLog = Join-Path $CampaignRunDir 'solve.log'
    foreach ($Selected in $SelectedCheckpoints) {
        $PerSeedRunLabel = '{0}_trainseed_{1}' -f $RunLabel, $Selected.TrainingSeed
        $RunnerArgs = @(
            '-u',
            '.\cie\code\run_cie_benchmarks.py',
            "--manifest=$ManifestPath",
            "--output_dir=$CampaignRunDir",
            "--solution_dir=$CampaignSolutionDir",
            '--methods=proposed',
            '--splits=mode_cleaning_crossover',
            '--suites=all',
            "--seeds=$SolverSeedArgument",
            "--training_seed=$($Selected.TrainingSeed)",
            "--run_label=$PerSeedRunLabel",
            "--time_limit=$TimeLimitText",
            '--stability_profile=stage2_off',
            '--device=cuda:0',
            "--memory_limit_mb=$MemoryLimitText",
            '--warm_start=auto',
            '--reuse_existing_solution_as_warm_start',
            '--scip_emphasis=optimality',
            "--scip_heuristics_profile=$ScipHeuristicsProfile",
            "--scip_nonroot_separation_rounds=$ScipNonrootSeparationRounds",
            "--scip_verbosity=$ScipVerbosity",
            '--sel_cuts_percent=0.2',
            '--decode_type=beam_search',
            '--policy_type=with_token',
            '--cutsel_max_candidates=128',
            '--cutsel_max_selected_cuts=16',
            '--structure_pool_factor=2.0',
            '--structure_anchor_ratio=0.25',
            '--structure_quality_weight=0.35',
            '--structure_policy_weight=0.20',
            '--structure_coverage_weight=0.25',
            '--structure_representation_weight=0.20',
            "--proposed_config=$ProposedConfig",
            "--proposed_model=$($Selected.Checkpoint)",
            '--fail_on_empty_suite'
        )
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
                Tee-Object -FilePath $SolveLog -Append
            $SolveExitCode = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $PreviousErrorActionPreference
        }
        if ($SolveExitCode -ne 0) {
            throw "Mode/cleaning crossover solve failed for training seed $($Selected.TrainingSeed). Full log: $SolveLog"
        }
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
    throw 'Independent SCIP/physical validation failed for the mode/cleaning crossover campaign.'
}

$MetricsPath = Join-Path $CampaignValidationDir 'cie_manufacturing_metrics.json'
$SummaryArgs = @(
    '.\JMS\analyze_mode_cleaning_crossover.py',
    "--metrics=$MetricsPath",
    "--output_dir=$CampaignSummaryDir",
    "--wafer_counts=$WaferCounts",
    "--cleaning_intervals=$CleaningIntervals",
    "--solver_seeds=$SolverSeeds",
    "--training_seeds=$TrainingSeeds",
    '--bridge_time=4',
    '--gap_tolerance=1e-8',
    '--objective_tolerance=1e-3',
    '--require_exact'
)
& $Python @SummaryArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Full exact-certificate table is incomplete. Saved solves and validation outputs are retained; inspect bounds and physical checks before drawing mode-ordering conclusions.'
}

$ReportPath = Join-Path $CampaignSummaryDir 'mode_cleaning_crossover.md'
Write-Host "Exact mode/cleaning crossover report: $(Join-Path $ProjectRoot $ReportPath)"
