param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('check', 'quick', 'generate-data', 'train-hem', 'train-a3c', 'train-feature-only', 'train-proposed', 'tune-acs', 'benchmark', 'benchmark-mechanism', 'benchmark-all', 'paper')]
    [string]$Stage,

    [string]$Seeds = '1,2,3,4,5',
    [int]$TimeLimit = 600,
    [string]$HemModel = '',
    [string]$A3cModel = '',
    [string]$FeatureOnlyModel = '',
    [string]$ProposedModel = '',
    [string]$AcsWeights = '',
    [ValidateSet('auto', 'none')]
    [string]$WarmStart = 'auto',
    [string]$ResumeModel = '',
    [int]$StartEpoch = -1,
    [double]$GridStep = 0.25,
    [int]$MaxInstances = 0,
    [string]$Suites = 'petri_large,petri_wafer100_stress',
    [ValidatePattern('^cuda:\d+$')]
    [string]$GpuDevice = 'cuda:0'
)

$ErrorActionPreference = 'Stop'
$AaaiRoot = $PSScriptRoot
$RepoRoot = Split-Path $AaaiRoot -Parent
Set-Location $RepoRoot

function Run-Python {
    param([string[]]$Arguments)
    Write-Host "`n> python $($Arguments -join ' ')" -ForegroundColor Cyan
    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE"
    }
}

function Get-EpochCheckpoints {
    param([string[]]$Folders, [int]$Epoch = 60)
    $files = @()
    foreach ($folder in $Folders) {
        if (-not (Test-Path -LiteralPath $folder)) { continue }
        $variants = Get-ChildItem -LiteralPath $folder -Recurse -File -Filter 'variant.json'
        foreach ($variant in $variants) {
            $epochFile = Join-Path $variant.Directory.FullName "itr_$Epoch.pkl"
            $paramsFile = Join-Path $variant.Directory.FullName 'params.pkl'
            if (Test-Path -LiteralPath $epochFile) {
                $files += Get-Item -LiteralPath $epochFile
            } elseif (Test-Path -LiteralPath $paramsFile) {
                try {
                    $metadata = Get-Content -LiteralPath $variant.FullName -Raw | ConvertFrom-Json
                    if ([int]$metadata.algorithm.num_epochs -le $Epoch) {
                        $files += Get-Item -LiteralPath $paramsFile
                    }
                } catch {
                    Write-Warning "Ignoring checkpoint with unreadable variant.json: $($variant.FullName)"
                }
            }
        }
    }
    return @($files | Sort-Object LastWriteTime)
}

function Find-LatestCheckpoint {
    param([string[]]$Folders, [int]$Epoch = 60)
    $file = Get-EpochCheckpoints $Folders $Epoch | Select-Object -Last 1
    if ($null -eq $file) { return '' }
    return $file.FullName
}

function Find-CheckpointsBySeed {
    param([string[]]$Folders, [int]$Epoch = 60)
    $map = @{}
    $files = Get-EpochCheckpoints $Folders $Epoch
    foreach ($file in $files) {
        $variantPath = Join-Path $file.Directory.FullName 'variant.json'
        try {
            $variant = Get-Content -LiteralPath $variantPath -Raw | ConvertFrom-Json
            $seed = $variant.parser_args.seed
            if ($null -eq $seed) { $seed = $variant.experiment.seed }
            $map[[int]$seed] = $file.FullName
        } catch {
            Write-Warning "Ignoring checkpoint with no readable training seed: $($file.FullName)"
        }
    }
    return $map
}

function Resolve-AcsWeights {
    if ($AcsWeights) { return $AcsWeights }
    $file = Get-ChildItem 'aaai/results/acs_tuning' -File -Filter 'acs_grid_*.json' -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime |
        Select-Object -Last 1
    if ($null -eq $file) {
        throw 'No completed ACS tuning JSON found. Finish tune-acs first or pass -AcsWeights "d,e,i,o".'
    }
    $payload = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
    $weights = $payload.best_weights
    $resolved = @(
        $weights.dircutoffdistweight,
        $weights.efficacyweight,
        $weights.intsupportweight,
        $weights.objparalweight
    ) -join ','
    Write-Host "ACS tuning result: $($file.FullName)"
    Write-Host "ACS weights: $resolved"
    return $resolved
}

function Require-Cuda {
    param([string]$Workload)
    Write-Host "Verifying GPU for $Workload on $GpuDevice..." -ForegroundColor Cyan
    & python -c "import torch; d=torch.device('$GpuDevice'); assert torch.cuda.is_available(), 'CUDA is unavailable: install a CUDA-enabled PyTorch build and verify nvidia-smi.'; assert d.index is None or d.index < torch.cuda.device_count(), f'{d} is not available; found {torch.cuda.device_count()} CUDA device(s).'; print('Using GPU:', torch.cuda.get_device_name(d))"
    if ($LASTEXITCODE -ne 0) {
        throw "$Workload requires CUDA. Run '.\aaai\run_aaai.ps1 -Stage check' after installing CUDA PyTorch."
    }
}

if ($Stage -eq 'check') {
    Write-Host 'AAAI-27 environment check' -ForegroundColor Green
    Write-Host "Repository: $RepoRoot"
    Write-Host "AAAI workspace: $AaaiRoot"
    Run-Python @('-c', "import sys, numpy, torch, pyscipopt; print('Python:', sys.version); print('NumPy:', numpy.__version__); print('PyTorch:', torch.__version__); print('CUDA available:', torch.cuda.is_available()); print('PySCIPOpt:', pyscipopt.__version__)")
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        & nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    } else {
        Write-Host 'nvidia-smi not found. CPU runs are still possible.' -ForegroundColor Yellow
    }
    Run-Python @('aaai/code/run_aaai27_benchmarks.py', '--help')
    Write-Host "`nEnvironment check completed." -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'quick') {
    Write-Host 'Generating tiny demonstration instances...' -ForegroundColor Green
    Run-Python @(
        'aaai/code/generate_aaai27_petri_suites.py',
        '--profile', 'quick',
        '--output_dir', 'aaai/data/quick_demo/submodular_petri',
        '--warm_start_time_limit', '30'
    )
    Run-Python @(
        'aaai/code/generate_aaai27_milp_families.py',
        '--output_dir', 'aaai/data/quick_demo/milp',
        '--train_instances', '0',
        '--validation_instances', '1',
        '--test_instances', '1',
        '--scales', 'small',
        '--seed', '2027'
    )
    Write-Host 'Running SCIP and ACS smoke tests. These numbers are NOT paper results.' -ForegroundColor Yellow
    Run-Python @(
        'aaai/code/run_aaai27_benchmarks.py',
        '--manifest', 'aaai/configs/aaai27_quick_suites.json',
        '--suites', 'all',
        '--methods', 'scip_default,adaptive_cutsel',
        '--seeds', '1',
        '--time_limit', '5',
        '--node_limit', '1',
        '--max_instances_per_suite', '1',
        '--output_dir', 'aaai/results/quick_demo'
    )
    Write-Host "`nQuick demo completed. Open aaai/results/quick_demo." -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'generate-data') {
    Run-Python @(
        'aaai/code/generate_aaai27_petri_suites.py',
        '--profile', 'full',
        '--output_dir', 'aaai/data/petri_submodular',
        '--warm_start_time_limit', '120'
    )
    Run-Python @(
        'aaai/code/generate_aaai27_milp_families.py',
        '--train_instances', '20',
        '--validation_instances', '5',
        '--test_instances', '10',
        '--scales', 'small,medium,large',
        '--seed', '2027'
    )
    Write-Host "`nFull data generation completed under aaai/data." -ForegroundColor Green
    exit 0
}

if ($Stage -in @('train-hem', 'train-a3c', 'train-feature-only', 'train-proposed')) {
    Require-Cuda $Stage
    $isHem = $Stage -eq 'train-hem'
    $isFeatureOnly = $Stage -eq 'train-feature-only'
    $usePercentPolicy = if ($Stage -eq 'train-a3c') { 'False' } else { 'True' }
    if ($isHem) {
        $config = 'aaai/configs/aaai27_hem_submodular_train.json'
        $instanceType = 'aaai27_hem'
    } elseif ($Stage -eq 'train-a3c') {
        $config = 'aaai/configs/aaai27_a3c_train.json'
        $instanceType = 'aaai27_a3c'
    } elseif ($isFeatureOnly) {
        $config = 'aaai/configs/aaai27_feature_only_train.json'
        $instanceType = 'aaai27_feature_only'
    } else {
        $config = 'aaai/configs/aaai27_proposed_train.json'
        $instanceType = 'aaai27_proposed_submodular'
    }
    foreach ($seed in ($Seeds -split ',')) {
        $seed = $seed.Trim()
        if (-not $seed) { continue }
        $trainArguments = @(
            'parallel_reinforce_algorithm.py',
            '--config_file', $config,
            '--train_type', 'train',
            '--generate_petri_instance', 'False',
            '--single_instance_file', 'all',
            '--sel_cuts_percent', '0.2',
            '--reward_type', 'primaldualintegral',
            '--baseline_type', 'simple',
            '--policy_type', 'with_token',
            '--use_cutsel_percent_policy', $usePercentPolicy,
            '--seed', $seed,
            '--scip_seed', $seed,
            '--instance_type', $instanceType
        )
        if ($ResumeModel) {
            $trainArguments += @('--resume_model', $ResumeModel)
        }
        if ($StartEpoch -ge 0) {
            $trainArguments += @('--start_epoch', $StartEpoch.ToString())
        }
        Run-Python $trainArguments
    }
    Write-Host "`nTraining completed. Check aaai/models." -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'tune-acs') {
    Write-Host 'ACS tuning uses SCIP and remains CPU-only; GPU is not used in this stage.' -ForegroundColor Yellow
    Run-Python @(
        'aaai/code/tune_aaai27_acs.py',
        '--seeds', $Seeds,
        '--time_limit', $TimeLimit.ToString(),
        '--grid_step', $GridStep.ToString(),
        '--max_instances', $MaxInstances.ToString()
    )
    Write-Host "`nACS tuning completed under aaai/results/acs_tuning." -ForegroundColor Green
    exit 0
}

if ($Stage -in @('benchmark', 'benchmark-mechanism')) {
    Require-Cuda $Stage
    $isMechanism = $Stage -eq 'benchmark-mechanism'
    if (-not $HemModel) { $HemModel = Find-LatestCheckpoint @('aaai/models/final_ablation/hem', 'aaai/models/hem_submodular_data') }
    if (-not $ProposedModel) { $ProposedModel = Find-LatestCheckpoint @('aaai/models/final_ablation/proposed', 'aaai/models/proposed_submodular') }
    if ($isMechanism -and -not $FeatureOnlyModel) { $FeatureOnlyModel = Find-LatestCheckpoint @('aaai/models/final_ablation/feature_only') }
    if (-not $HemModel) { throw 'No HEM params.pkl found. Run: .\aaai\run_aaai.ps1 -Stage train-hem' }
    if (-not $ProposedModel) { throw 'No proposed params.pkl found. Run: .\aaai\run_aaai.ps1 -Stage train-proposed' }
    if ($isMechanism -and -not $FeatureOnlyModel) { throw 'No feature-only params.pkl found. Run: .\aaai\run_aaai.ps1 -Stage train-feature-only' }
    $benchmarkMethods = if ($isMechanism) {
        'hem,rdmct_feature_only,hem_structure,proposed'
    } else {
        'scip_default,adaptive_cutsel,hem,hem_beam,hem_structure,proposed'
    }
    $resolvedAcsWeights = if ($isMechanism) { '0,1,0,0' } else { Resolve-AcsWeights }
    $benchmarkOutput = if ($isMechanism) {
        'aaai/results/mechanism_ablation'
    } else {
        'aaai/results/final_benchmark'
    }
    Write-Host "HEM checkpoint: $HemModel"
    Write-Host "Proposed checkpoint: $ProposedModel"
    if ($isMechanism) { Write-Host "Feature-only checkpoint: $FeatureOnlyModel" }
    Run-Python @(
        'aaai/code/run_aaai27_benchmarks.py',
        '--splits', 'test',
        '--suites', $Suites,
        '--methods', $benchmarkMethods,
        '--seeds', $Seeds,
        '--time_limit', $TimeLimit.ToString(),
        '--max_instances_per_suite', $MaxInstances.ToString(),
        '--device', $GpuDevice,
        '--acs_weights', $resolvedAcsWeights,
        '--warm_start', $WarmStart,
        '--hem_model', $HemModel,
        '--feature_only_model', $FeatureOnlyModel,
        '--proposed_model', $ProposedModel,
        '--output_dir', $benchmarkOutput
    )
    Write-Host "`nBenchmark completed under $benchmarkOutput." -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'benchmark-all') {
    Require-Cuda $Stage
    $campaignId = "petri_ablation_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    $runDir = "aaai/results/final_benchmark/$campaignId/runs"
    $combinedDir = "aaai/results/final_benchmark/$campaignId/combined"
    $hemMap = Find-CheckpointsBySeed @('aaai/models/final_ablation/hem', 'aaai/models/hem_submodular_data')
    $featureOnlyMap = Find-CheckpointsBySeed @('aaai/models/final_ablation/feature_only')
    $proposedMap = Find-CheckpointsBySeed @('aaai/models/final_ablation/proposed', 'aaai/models/proposed_submodular')
    $resolvedAcsWeights = Resolve-AcsWeights
    $trainingSeeds = @(
        $hemMap.Keys |
        Where-Object { $featureOnlyMap.ContainsKey($_) -and $proposedMap.ContainsKey($_) } |
        Sort-Object
    )
    if ($trainingSeeds.Count -eq 0) {
        throw 'No matching HEM/Proposed training seeds found. Expected checkpoint paths containing --s-<seed>.'
    }
    $trainingSeedIndex = 0
    foreach ($trainingSeed in $trainingSeeds) {
        $benchmarkMethods = if ($trainingSeedIndex -eq 0) {
            'scip_default,adaptive_cutsel,hem,rdmct_feature_only,hem_beam,hem_structure,proposed'
        } else {
            'hem,rdmct_feature_only,hem_beam,hem_structure,proposed'
        }
        Write-Host "`nTesting training seed $trainingSeed" -ForegroundColor Green
        Run-Python @(
            'aaai/code/run_aaai27_benchmarks.py',
            '--splits', 'test',
            '--suites', $Suites,
            '--methods', $benchmarkMethods,
            '--seeds', $Seeds,
            '--training_seed', $trainingSeed.ToString(),
            '--run_label', "trainseed_$trainingSeed",
            '--time_limit', $TimeLimit.ToString(),
            '--max_instances_per_suite', $MaxInstances.ToString(),
            '--device', $GpuDevice,
            '--acs_weights', $resolvedAcsWeights,
            '--warm_start', $WarmStart,
            '--hem_model', $hemMap[$trainingSeed],
            '--feature_only_model', $featureOnlyMap[$trainingSeed],
            '--proposed_model', $proposedMap[$trainingSeed],
            '--output_dir', $runDir
        )
        $trainingSeedIndex += 1
    }
    Run-Python @(
        'aaai/code/combine_aaai27_runs.py',
        '--input_dir', $runDir,
        '--output_dir', $combinedDir
    )
    Write-Host "`nAll training seeds were combined under $combinedDir." -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'paper') {
    Run-Python @('aaai/code/plot_aaai27_pipeline.py')
    Push-Location 'aaai/products'
    try {
        & pdflatex -interaction=nonstopmode -halt-on-error rdmct_aaai27.tex
        if ($LASTEXITCODE -ne 0) { throw 'First pdflatex pass failed.' }
        & bibtex rdmct_aaai27
        if ($LASTEXITCODE -ne 0) { throw 'BibTeX failed.' }
        & pdflatex -interaction=nonstopmode -halt-on-error rdmct_aaai27.tex
        if ($LASTEXITCODE -ne 0) { throw 'Second pdflatex pass failed.' }
        & pdflatex -interaction=nonstopmode -halt-on-error rdmct_aaai27.tex
        if ($LASTEXITCODE -ne 0) { throw 'Final pdflatex pass failed.' }
    } finally {
        Pop-Location
    }
    Write-Host "`nPaper compiled: aaai/products/rdmct_aaai27.pdf" -ForegroundColor Green
}
