param(
    [switch]$SkipGeneration,
    [double]$TimeLimit = 1200,
    [string]$Checkpoint = 'cie\models\proposed\cie_proposed_all_cie_proposed\cie_proposed_all_cie_proposed_2026_08_02_14_55_21_0000--s-1\itr_60.pkl'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

if ($env:CONDA_DEFAULT_ENV -ne 'a3cenv') {
    throw 'Activate the required environment first: conda activate a3cenv'
}
python -c 'import torch,pyscipopt; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0), pyscipopt.__version__)'
if ($LASTEXITCODE -ne 0) { throw 'a3cenv/CUDA preflight failed.' }
if (-not (Test-Path -LiteralPath $Checkpoint -PathType Leaf)) {
    throw ('Frozen Proposed checkpoint is missing: {0}' -f $Checkpoint)
}

function New-Wafer50Instance {
    param(
        [string]$Name,
        [int]$Wafers41,
        [int]$Wafers22,
        [int]$WarmStartSeconds
    )
    $Arguments = @(
        'petri_mip_generator.py',
        '--output_dir', 'generated_instances\jms_wafer50',
        '--instance_name', $Name,
        '--warm_start_time_limit', $WarmStartSeconds,
        '--num_batches', 15,
        '--num_pm', 2,
        '--num_steps', 13,
        '--total_wafers', 50,
        '--mode_4x1_wafers', $Wafers41,
        '--mode_2x2_wafers', $Wafers22,
        '--pec_pool_size', 8,
        '--batch_size', 4,
        '--big_m', 10000,
        '--pm_transfer_gap', 1,
        '--pm_rotation_time_180', 2,
        '--pair_transfer_time', 4,
        '--atr_transfer_time', 3,
        '--atr_return_time', 3,
        '--atr_capacity', 2,
        '--vtr_capacity', 4,
        '--aligner_time', 20,
        '--llupper_time', 30,
        '--lllower_time', 25,
        '--full_process_time', 180,
        '--mix_boundary_process_time', 180,
        '--mix_internal_process_time', 180,
        '--cleaning_interval', 10,
        '--cleaning_process_time', 500,
        '--max_module_residency_time', 10000,
        '--max_robot_residency_time', 10000,
        '--max_schedule_wait_time', 0,
        '--schedule_stability_objective', 'compact_resource_idle',
        '--process_mode', 'auto'
    )
    & python @Arguments
    if ($LASTEXITCODE -ne 0) { throw ('Generation failed: {0}' -f $Name) }
}

if (-not $SkipGeneration) {
    New-Wafer50Instance wafer50_22_20260825.lp 0 50 600
    New-Wafer50Instance wafer50_41_20260825.lp 50 0 0
    New-Wafer50Instance wafer50_mix_25_25_20260825.lp 25 25 600
}

$InstanceDir = 'generated_instances\jms_wafer50'
$RequiredInstances = @(
    'wafer50_22_20260825.lp',
    'wafer50_41_20260825.lp',
    'wafer50_mix_25_25_20260825.lp'
)
foreach ($Name in $RequiredInstances) {
    $Path = Join-Path $InstanceDir $Name
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw ('Frozen instance is missing: {0}' -f $Path)
    }
}

$ExpectedHashes = @{
    'wafer50_22_20260825.lp' = 'e014946329b62cca8e3b6c22d55c9466df93e7591207a10e44f1da532fdfe9b8'
    'wafer50_41_20260825.lp' = '4d247de564690a718139616be86e87b94220f64dd7373e71898930d776280484'
    'wafer50_mix_25_25_20260825.lp' = '85b8f087837d195eb1958a6da4ff5d224fc1001c3f9b8d8e3557d94ea2107873'
}
foreach ($Name in $RequiredInstances) {
    $Path = Join-Path $InstanceDir $Name
    $ActualHash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ActualHash -ne $ExpectedHashes[$Name]) {
        throw ('Frozen instance SHA-256 mismatch: {0}' -f $Path)
    }
}
$ExpectedCheckpointHash = '23961d2d9f09473982a79271642fca1d6e76cd0bf3837240d5e38a2361d824ce'
$ActualCheckpointHash = (Get-FileHash -LiteralPath $Checkpoint -Algorithm SHA256).Hash.ToLowerInvariant()
if ($ActualCheckpointHash -ne $ExpectedCheckpointHash) {
    throw ('Frozen checkpoint SHA-256 mismatch: {0}' -f $Checkpoint)
}

$ResultRoot = 'JMS\results\wafer50_gantt'
New-Item -ItemType Directory -Force $ResultRoot | Out-Null
Get-FileHash (Join-Path $InstanceDir '*.lp') -Algorithm SHA256 |
    Export-Csv (Join-Path $ResultRoot 'instance_sha256.csv') -NoTypeInformation
Get-FileHash -LiteralPath $Checkpoint -Algorithm SHA256 |
    Export-Csv (Join-Path $ResultRoot 'checkpoint_sha256.csv') -NoTypeInformation

python -u cie\code\run_cie_benchmarks.py `
    --manifest JMS\wafer50_gantt_suites.json `
    --splits wafer50_gantt `
    --suites all `
    --methods proposed `
    --seeds 1 `
    --training_seed 1 `
    --run_label wafer50_gantt_20260825 `
    --time_limit $TimeLimit `
    --stability_profile full `
    --memory_limit_mb 4096 `
    --device cuda:0 `
    --warm_start auto `
    --cutsel_max_candidates 128 `
    --cutsel_max_selected_cuts 16 `
    --proposed_config cie\configs\cie_proposed_inference.json `
    --proposed_model $Checkpoint `
    --output_dir JMS\results\wafer50_gantt\runs `
    --solution_dir JMS\results\wafer50_gantt\solutions `
    --fail_on_empty_suite
if ($LASTEXITCODE -ne 0) { throw 'The wafer50 Proposed solve failed.' }

python cie\code\analyze_cie_solutions.py `
    --input_dir JMS\results\wafer50_gantt\runs `
    --output_dir JMS\results\wafer50_gantt\validation `
    --validate `
    --fail_on_invalid
if ($LASTEXITCODE -ne 0) { throw 'Independent SCIP validation failed.' }

$Exports = @(
    @{
        Instance = 'wafer50_22_20260825.lp'
        Suite = 'wafer50_pure22'
    },
    @{
        Instance = 'wafer50_41_20260825.lp'
        Suite = 'wafer50_pure41'
    },
    @{
        Instance = 'wafer50_mix_25_25_20260825.lp'
        Suite = 'wafer50_mixed11'
    }
)
foreach ($Item in $Exports) {
    $Stem = [IO.Path]::GetFileNameWithoutExtension($Item.Instance)
    $SolutionName = '{0}__{1}__proposed__solverseed_1__trainseed_1__wafer50_gantt_20260825.sol' -f $Item.Suite,$Stem
    $SolutionPath = Join-Path (Join-Path $ResultRoot 'solutions') $SolutionName
    $GanttRoot = Join-Path (Join-Path $ResultRoot 'gantt') $Stem
    $JsonPath = Join-Path $GanttRoot ($Stem + '_validated_solutions.json')
    if (-not (Test-Path -LiteralPath $SolutionPath -PathType Leaf)) {
        throw ('Saved SCIP solution is missing: {0}' -f $SolutionPath)
    }
    python cie\code\export_cie_gantt_json.py `
        --instance (Join-Path $InstanceDir $Item.Instance) `
        --solution $SolutionPath `
        --output_json $JsonPath
    if ($LASTEXITCODE -ne 0) { throw ('Gantt JSON export failed: {0}' -f $Stem) }
    python petri_gantt.py `
        --solution_json $JsonPath `
        --output_dir $GanttRoot `
        --view all
    if ($LASTEXITCODE -ne 0) { throw ('Gantt rendering failed: {0}' -f $Stem) }
}

python -m pytest `
    tests\test_petri_gantt_paths.py `
    RL-SAT\tests\test_compatible_petri_gantt.py `
    -q
if ($LASTEXITCODE -ne 0) { throw 'Gantt regression tests failed.' }

Write-Host ('Validated wafer50 Gantt evidence: {0}' -f (Join-Path $ProjectRoot $ResultRoot))
