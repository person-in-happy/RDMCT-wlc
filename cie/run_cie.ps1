param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('check','smoke','gpu-smoke','model-evidence','generate-validation','generate-core','generate-sensitivity','generate-ood','generate-all','warmstarts-core','warmstarts-sensitivity','warmstarts-ood','train-hem','train-feature-only','train-proposed','train-all','freeze-checkpoints','tune-acs','benchmark-validation','benchmark-main','benchmark-stability','benchmark-doe','benchmark-spbs','benchmark-sensitivity','benchmark-ood','analyze')]
    [string]$Stage,
    [string]$Seeds = '1,2,3,4,5,6,7,8,9,10',
    [int]$TimeLimit = 600,
    [int]$WarmStartTimeLimit = 180,
    [string]$GpuDevice = 'cuda:0',
    [int]$MaxInstances = 0,
    [ValidateRange(512,65536)]
    [int]$MemoryLimitMB = 4096,
    [ValidatePattern('^[A-Za-z0-9_-]*$')]
    [string]$CampaignId = '',
    [ValidatePattern('^[A-Za-z0-9_-]*$')]
    [string]$ShardTag = '',
    [ValidatePattern('^[0-9, ]*$')]
    [string]$TrainingSeeds = '',
    [ValidateSet('both','none','auto')]
    [string]$SpbsWarmStarts = 'both',
    [string]$AnalysisInput = 'cie/results',
    [string]$AnalysisOutput = 'cie/results/analysis',
    [string]$ReferenceMethod = 'proposed',
    [string]$AcsWeightsFile = '',
    [string]$CheckpointManifest = 'cie/results/repro_manifest/selected_checkpoint_manifest.csv',
    [switch]$AllowLegacyCheckpoints
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot
$Manifest = 'cie/configs/cie_benchmark_suites.json'

function Run-Python {
    param([string[]]$Arguments)
    Write-Host "`n> python $($Arguments -join ' ')" -ForegroundColor Cyan
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        # Keep the native process attached directly to the caller's stdout/stderr.
        # Piping verbose benchmark output through Out-Host creates large numbers of
        # PowerShell objects and can exhaust RAM in long-running parallel jobs.
        & python @Arguments
        $pythonExitCode = $LASTEXITCODE
        if ($null -eq $pythonExitCode) { $pythonExitCode = 1 }
    } finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($pythonExitCode -ne 0) { throw "Python failed with exit code $pythonExitCode" }
}

function Require-Cuda {
    Run-Python @('-c', "import sys,torch; assert torch.cuda.is_available(), 'CUDA-enabled PyTorch is required'; d=torch.device('$GpuDevice'); p=torch.cuda.get_device_properties(d); print('python',sys.executable); print('torch',torch.__version__); print('cuda_runtime',torch.version.cuda); print('gpu',p.name); print('capability',torch.cuda.get_device_capability(d)); print('vram_GB',round(p.total_memory/1024**3,2))")
}

function Get-CampaignRoot {
    param([string]$Campaign)
    if ($CampaignId) {
        $root = "cie/results/$Campaign/$CampaignId"
        if ($ShardTag) { $root = "$root/$ShardTag" }
        return $root
    }
    $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    if ($ShardTag) { $stamp = "${stamp}_$ShardTag" }
    return "cie/results/$Campaign/$stamp"
}

function Get-CheckpointsBySeed {
    param([string[]]$Folders, [int]$Epoch = 60)
    $map = @{}
    foreach ($folder in $Folders) {
        if (-not (Test-Path -LiteralPath $folder)) { continue }
        foreach ($variant in @(Get-ChildItem -LiteralPath $folder -Recurse -File -Filter variant.json | Sort-Object LastWriteTime)) {
            try {
                $payload = Get-Content -LiteralPath $variant.FullName -Raw | ConvertFrom-Json
                $seed = $payload.parser_args.seed
                if ($null -eq $seed) { $seed = $payload.experiment.seed }
                if (-not $AllowLegacyCheckpoints) {
                    $experimentSeed = $payload.experiment.seed
                    $scipSeed = $payload.parser_args.scip_seed
                    $trainingPath = [string]$payload.env.instance_file_path
                    $normalizedTrainingPath = $trainingPath.Replace('/','\').ToLowerInvariant()
                    $isCurrentTrainingPath = $normalizedTrainingPath.EndsWith('cie\data\policy_training\train')
                    if (
                        $null -eq $seed -or
                        $null -eq $experimentSeed -or
                        $null -eq $scipSeed -or
                        [int]$seed -ne [int]$experimentSeed -or
                        [int]$seed -ne [int]$scipSeed -or
                        -not $isCurrentTrainingPath
                    ) {
                        Write-Warning "Skipping legacy/non-auditable checkpoint metadata: $($variant.FullName)"
                        continue
                    }
                }
                $checkpoint = Join-Path $variant.Directory.FullName "itr_$Epoch.pkl"
                if (-not (Test-Path -LiteralPath $checkpoint)) {
                    $checkpoint = Join-Path $variant.Directory.FullName 'params.pkl'
                }
                if (Test-Path -LiteralPath $checkpoint) { $map[[int]$seed] = $checkpoint }
            } catch { Write-Warning "Skipping unreadable checkpoint metadata: $($variant.FullName)" }
        }
    }
    return $map
}

function Get-AcsWeights {
    $file = if ($AcsWeightsFile) {
        if (-not (Test-Path -LiteralPath $AcsWeightsFile -PathType Leaf)) {
            throw "ACS weights file not found: $AcsWeightsFile"
        }
        Get-Item -LiteralPath $AcsWeightsFile
    } else {
        Write-Warning 'No -AcsWeightsFile was supplied; using the newest tuning JSON. Formal campaigns should pass an explicit frozen file.'
        Get-ChildItem 'cie/results/acs_tuning' -File -Filter 'acs_grid_*.json' -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime | Select-Object -Last 1
    }
    if ($null -eq $file) { throw "Run '.\cie\run_cie.ps1 -Stage tune-acs' first." }
    $payload = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
    return @(
        $payload.best_weights.dircutoffdistweight,
        $payload.best_weights.efficacyweight,
        $payload.best_weights.intsupportweight,
        $payload.best_weights.objparalweight
    ) -join ','
}

function Resolve-ManifestAssetPath {
    param([Parameter(Mandatory = $true)][string]$Path)
    if ([IO.Path]::IsPathRooted($Path)) {
        return [IO.Path]::GetFullPath($Path)
    }
    return [IO.Path]::GetFullPath((Join-Path -Path (Get-Location).Path -ChildPath $Path))
}

function Get-FrozenCheckpointsBySeed {
    param([Parameter(Mandatory = $true)][string]$Family)
    if (-not (Test-Path -LiteralPath $CheckpointManifest -PathType Leaf)) {
        throw ('Frozen checkpoint manifest not found: ' + $CheckpointManifest + '. Run -Stage freeze-checkpoints first.')
    }
    $rows = @(Import-Csv -LiteralPath $CheckpointManifest | Where-Object { $_.family -eq $Family })
    if ($rows.Count -ne 5) {
        throw ('Checkpoint manifest requires exactly five rows for ' + $Family + '; found ' + $rows.Count)
    }
    $map = @{}
    foreach ($row in $rows) {
        $seed = [int]$row.training_seed
        if ($map.ContainsKey($seed)) { throw ('Duplicate checkpoint manifest seed: ' + $Family + '/' + $seed) }
        $checkpoint = Resolve-ManifestAssetPath -Path ([string]$row.checkpoint)
        $variant = Resolve-ManifestAssetPath -Path ([string]$row.variant)
        if ([IO.Path]::GetFileName($checkpoint) -ne 'itr_60.pkl') { throw ('Formal checkpoint must be itr_60.pkl: ' + $checkpoint) }
        if (-not (Test-Path -LiteralPath $checkpoint -PathType Leaf)) { throw ('Missing checkpoint: ' + $checkpoint) }
        if (-not (Test-Path -LiteralPath $variant -PathType Leaf)) { throw ('Missing variant: ' + $variant) }
        $checkpointHash = (Get-FileHash -LiteralPath $checkpoint -Algorithm SHA256).Hash
        $variantHash = (Get-FileHash -LiteralPath $variant -Algorithm SHA256).Hash
        if ($checkpointHash -ne [string]$row.checkpoint_sha256) { throw ('Checkpoint hash mismatch: ' + $checkpoint) }
        if ($variantHash -ne [string]$row.variant_sha256) { throw ('Variant hash mismatch: ' + $variant) }
        $metadata = Get-Content -LiteralPath $variant -Raw | ConvertFrom-Json
        $trainingPath = [string]$metadata.env.instance_file_path
        $validPath = $trainingPath.Replace('/',[string][char]92).ToLowerInvariant().EndsWith('cie\data\policy_training\train')
        if ([int]$metadata.experiment.seed -ne $seed -or [int]$metadata.parser_args.seed -ne $seed -or [int]$metadata.parser_args.scip_seed -ne $seed -or -not $validPath) {
            throw ('Checkpoint metadata mismatch: ' + $Family + '/' + $seed)
        }
        $map[$seed] = $checkpoint
    }
    if ((@($map.Keys | Sort-Object) -join ',') -ne '1,2,3,4,5') {
        throw ('Checkpoint manifest seeds for ' + $Family + ' must be exactly 1,2,3,4,5.')
    }
    return $map
}

function Run-LearnedCampaign {
    param([string]$Suite, [string]$Campaign, [int]$Limit)
    Require-Cuda
    $hem = Get-FrozenCheckpointsBySeed -Family 'hem'
    $feature = Get-FrozenCheckpointsBySeed -Family 'feature_only'
    $proposed = Get-FrozenCheckpointsBySeed -Family 'proposed'
    $availableTrainingSeeds = @($hem.Keys | Where-Object { $feature.ContainsKey($_) -and $proposed.ContainsKey($_) } | Sort-Object)
    if ($availableTrainingSeeds.Count -lt 5) {
        throw "C&IE requires five matched, auditable HEM/feature-only/Proposed checkpoints; found $($availableTrainingSeeds.Count). Run train-all. Use -AllowLegacyCheckpoints only for non-paper smoke/diagnostics."
    }
    $trainingSeeds = if ([string]::IsNullOrWhiteSpace($TrainingSeeds)) {
        $availableTrainingSeeds
    } else {
        @($TrainingSeeds -split ',' | ForEach-Object { [int]$_.Trim() })
    }
    if ($trainingSeeds.Count -eq 0) { throw 'At least one training seed is required.' }
    $invalidTrainingSeeds = @($trainingSeeds | Where-Object { $availableTrainingSeeds -notcontains $_ })
    if ($invalidTrainingSeeds.Count -gt 0) {
        throw "Requested training seeds have no matched checkpoints: $($invalidTrainingSeeds -join ',')"
    }
    $root = Get-CampaignRoot $Campaign
    $runDir = "$root/runs"
    $solutionDir = "$root/solutions"
    $acs = Get-AcsWeights
    foreach ($trainingSeed in $trainingSeeds) {
        $methods = if ($trainingSeed -eq $availableTrainingSeeds[0]) {
            'scip_default,adaptive_cutsel,hem,rdmct_feature_only,hem_beam,hem_structure,proposed'
        } else {
            'hem,rdmct_feature_only,hem_beam,hem_structure,proposed'
        }
        Run-Python @(
            'cie/code/run_cie_benchmarks.py', '--manifest', $Manifest,
            '--splits', 'test', '--suites', $Suite, '--methods', $methods,
            '--seeds', $Seeds, '--training_seed', $trainingSeed.ToString(),
            '--run_label', "trainseed_$trainingSeed", '--time_limit', $Limit.ToString(),
            '--stability_profile', 'full',
            '--memory_limit_mb', $MemoryLimitMB.ToString(),
            '--max_instances_per_suite', $MaxInstances.ToString(), '--device', $GpuDevice,
            '--acs_weights', $acs, '--warm_start', 'auto',
            '--hem_model', $hem[$trainingSeed], '--feature_only_model', $feature[$trainingSeed],
            '--proposed_model', $proposed[$trainingSeed], '--output_dir', $runDir,
            '--solution_dir', $solutionDir, '--fail_on_empty_suite'
        )
    }
    Run-Python @('cie/code/combine_cie_runs.py','--input_dir',$runDir,'--output_dir',"$root/combined")
    Write-Host "Campaign output: $root" -ForegroundColor Green
}

function Run-StabilityCampaign {
    Require-Cuda
    $proposed = Get-FrozenCheckpointsBySeed -Family 'proposed'
    $availableTrainingSeeds = @($proposed.Keys | Sort-Object)
    if ($availableTrainingSeeds.Count -lt 5) {
        throw "C&IE stability ablation requires five auditable Proposed checkpoints; found $($availableTrainingSeeds.Count). Run train-all first."
    }
    $trainingSeeds = if ([string]::IsNullOrWhiteSpace($TrainingSeeds)) {
        $availableTrainingSeeds
    } else {
        @($TrainingSeeds -split ',' | ForEach-Object { [int]$_.Trim() })
    }
    if ($trainingSeeds.Count -eq 0) { throw 'At least one training seed is required.' }
    $invalidTrainingSeeds = @($trainingSeeds | Where-Object { $availableTrainingSeeds -notcontains $_ })
    if ($invalidTrainingSeeds.Count -gt 0) {
        throw "Requested training seeds have no Proposed checkpoint: $($invalidTrainingSeeds -join ',')"
    }

    $root = Get-CampaignRoot 'stability'
    $runDir = "$root/runs"
    $solutionDir = "$root/solutions"
    foreach ($profile in @('full','stage2_off','linear_off')) {
        foreach ($trainingSeed in $trainingSeeds) {
            Run-Python @(
                'cie/code/run_cie_benchmarks.py', '--manifest', $Manifest,
                '--splits', 'test', '--suites', 'cie_core_nominal',
                '--methods', 'proposed', '--seeds', $Seeds,
                '--training_seed', $trainingSeed.ToString(),
                '--run_label', "stability_${profile}_trainseed_$trainingSeed",
                '--stability_profile', $profile, '--time_limit', $TimeLimit.ToString(),
                '--memory_limit_mb', $MemoryLimitMB.ToString(),
                '--max_instances_per_suite', $MaxInstances.ToString(),
                '--device', $GpuDevice, '--warm_start', 'auto',
                '--proposed_model', $proposed[$trainingSeed],
                '--output_dir', $runDir, '--solution_dir', $solutionDir,
                '--fail_on_empty_suite'
            )
        }
    }
    Run-Python @('cie/code/combine_cie_runs.py','--input_dir',$runDir,'--output_dir',"$root/combined")
    Run-Python @(
        'cie/code/summarize_cie_benchmarks.py', '--input_dir', $runDir,
        '--output_dir', "$root/analysis", '--reference_method', 'proposed[full]'
    )
    Write-Host "Stability-ablation output: $root" -ForegroundColor Green
}

if ($Stage -eq 'check') {
    Run-Python @('-c', "import sys,numpy,torch,pyscipopt,scipy; print(sys.version); print('numpy',numpy.__version__); print('torch',torch.__version__); print('cuda',torch.cuda.is_available()); print('pyscipopt',pyscipopt.__version__); print('scipy',scipy.__version__)")
    Run-Python @('cie/code/generate_cie_instances.py','--help')
    Run-Python @('cie/code/run_cie_benchmarks.py','--help')
    Run-Python @('cie/code/combine_cie_runs.py','--help')
    Run-Python @('cie/code/tune_cie_acs.py','--help')
    Run-Python @('cie/code/analyze_cie_solutions.py','--help')
    Run-Python @('cie/code/summarize_cie_benchmarks.py','--help')
    exit 0
}

if ($Stage -eq 'smoke') {
    Run-Python @('cie/code/generate_cie_instances.py','--action','generate','--profile','validation')
    $root = "cie/results/smoke/$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Run-Python @('cie/code/run_cie_benchmarks.py','--manifest',$Manifest,'--splits','validation','--suites','cie_validation','--methods','scip_default','--seeds','1','--time_limit','30','--max_instances_per_suite','1','--warm_start','none','--output_dir',"$root/runs",'--solution_dir',"$root/solutions",'--fail_on_empty_suite')
    Run-Python @('cie/code/analyze_cie_solutions.py','--input_dir',"$root/runs",'--output_dir',"$root/analysis",'--validate','--fail_on_invalid')
    Run-Python @('cie/code/summarize_cie_benchmarks.py','--input_dir',"$root/runs",'--output_dir',"$root/analysis",'--reference_method','scip_default')
    exit 0
}

if ($Stage -eq 'model-evidence') {
    Run-Python @('-m','pytest','tests/test_compact_petri_model.py','-q')
    Run-Python @('cie/code/analyze_cie_model_scale.py','--manifest',$Manifest,'--output-dir','cie/results/model_evidence')
    exit 0
}

if ($Stage -eq 'gpu-smoke') {
    Require-Cuda
    $hem = Get-CheckpointsBySeed @('cie/models/hem')
    if (-not $hem.ContainsKey(1)) { throw 'No auditable HEM checkpoint for training seed 1 was found. Train it, or pass -AllowLegacyCheckpoints for a non-paper smoke only.' }
    Run-Python @('cie/code/generate_cie_instances.py','--action','generate','--profile','validation')
    $root = "cie/results/gpu_smoke/$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Run-Python @('cie/code/run_cie_benchmarks.py','--manifest',$Manifest,'--splits','validation','--suites','cie_validation','--methods','hem','--seeds','1','--training_seed','1','--run_label','gpu_smoke','--time_limit','30','--max_instances_per_suite','1','--device',$GpuDevice,'--warm_start','none','--hem_model',$hem[1],'--output_dir',"$root/runs",'--solution_dir',"$root/solutions",'--fail_on_empty_suite')
    Write-Host "GPU smoke output: $root" -ForegroundColor Green
    exit 0
}

$generateProfiles = @{
    'generate-validation'='validation'; 'generate-core'='core';
    'generate-sensitivity'='sensitivity'; 'generate-ood'='ood'; 'generate-all'='all'
}
if ($generateProfiles.ContainsKey($Stage)) {
    Run-Python @('cie/code/generate_cie_instances.py','--action','generate','--profile',$generateProfiles[$Stage])
    exit 0
}

$warmProfiles = @{
    'warmstarts-core'='core'; 'warmstarts-sensitivity'='sensitivity'; 'warmstarts-ood'='ood'
}
if ($warmProfiles.ContainsKey($Stage)) {
    Run-Python @('cie/code/generate_cie_instances.py','--action','warm-start','--profile',$warmProfiles[$Stage],'--warm_start_time_limit',$WarmStartTimeLimit.ToString(),'--memory_limit_mb',$MemoryLimitMB.ToString())
    exit 0
}

if ($Stage -in @('train-hem','train-feature-only','train-proposed','train-all')) {
    Require-Cuda
    $trainingProfiles = [ordered]@{
        'train-hem' = @('cie/configs/cie_hem_train.json','cie_hem')
        'train-feature-only' = @('cie/configs/cie_feature_only_train.json','cie_feature_only')
        'train-proposed' = @('cie/configs/cie_proposed_train.json','cie_proposed')
    }
    $selectedProfiles = if ($Stage -eq 'train-all') {
        @('train-hem','train-feature-only','train-proposed')
    } else {
        @($Stage)
    }
    foreach ($profileName in $selectedProfiles) {
        $profile = $trainingProfiles[$profileName]
        foreach ($seed in @($Seeds -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
            Run-Python @(
                'parallel_reinforce_algorithm.py',
                '--config_file',$profile[0],
                '--single_instance_file','all',
                '--instance_type',$profile[1],
                '--train_type','train',
                '--reward_type','primaldualintegral',
                '--baseline_type','simple',
                '--policy_type','with_token',
                '--use_cutsel_percent_policy','True',
                '--auto_resume',
                '--seed',$seed,
                '--scip_seed',$seed
            )
        }
    }
    exit 0
}

if ($Stage -eq 'freeze-checkpoints') {
    Run-Python @('cie/code/freeze_cie_checkpoints.py','--output',$CheckpointManifest,'--seeds','1,2,3,4,5','--epoch','60')
    foreach ($family in @('hem','feature_only','proposed')) {
        [void](Get-FrozenCheckpointsBySeed -Family $family)
    }
    Write-Host 'Frozen checkpoint preflight passed: 15 models and variants verified.' -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'tune-acs') {
    Run-Python @('cie/code/tune_cie_acs.py','--manifest',$Manifest,'--output_dir','cie/results/acs_tuning','--seeds','1,2,3,4,5','--time_limit','300','--grid_step','0.25','--memory_limit_mb',$MemoryLimitMB.ToString())
    exit 0
}

if ($Stage -eq 'benchmark-main') { Run-LearnedCampaign 'cie_core_nominal' 'main' $TimeLimit; exit 0 }
if ($Stage -eq 'benchmark-ood') { Run-LearnedCampaign 'cie_ood' 'ood' ([Math]::Max($TimeLimit,1200)); exit 0 }
if ($Stage -eq 'benchmark-stability') { Run-StabilityCampaign; exit 0 }

if ($Stage -eq 'benchmark-validation') {
    $root = Get-CampaignRoot 'validation'
    Run-Python @('cie/code/run_cie_benchmarks.py','--manifest',$Manifest,'--splits','validation','--suites','cie_validation','--methods','scip_default','--seeds',$Seeds,'--time_limit',$TimeLimit.ToString(),'--memory_limit_mb',$MemoryLimitMB.ToString(),'--max_instances_per_suite',$MaxInstances.ToString(),'--warm_start','none','--run_label','final_validation','--output_dir',"$root/runs",'--solution_dir',"$root/solutions",'--fail_on_empty_suite')
    Write-Host "Validation output: $root" -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'benchmark-doe') {
    $root = Get-CampaignRoot 'doe'
    Run-Python @('cie/code/run_cie_benchmarks.py','--manifest',$Manifest,'--splits','test','--suites','cie_core','--methods','scip_default','--seeds',$Seeds,'--time_limit',$TimeLimit.ToString(),'--memory_limit_mb',$MemoryLimitMB.ToString(),'--max_instances_per_suite',$MaxInstances.ToString(),'--warm_start','auto','--run_label','manufacturing_doe','--output_dir',"$root/runs",'--solution_dir',"$root/solutions",'--fail_on_empty_suite')
    Write-Host "DOE output: $root" -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'benchmark-spbs') {
    $root = Get-CampaignRoot 'spbs'
    $warmStarts = if ($SpbsWarmStarts -eq 'both') { @('none','auto') } else { @($SpbsWarmStarts) }
    foreach ($warm in $warmStarts) {
        Run-Python @('cie/code/run_cie_benchmarks.py','--manifest',$Manifest,'--splits','test','--suites','cie_core_spbs','--methods','scip_default','--seeds',$Seeds,'--time_limit',$TimeLimit.ToString(),'--memory_limit_mb',$MemoryLimitMB.ToString(),'--max_instances_per_suite',$MaxInstances.ToString(),'--warm_start',$warm,'--run_label',"spbs_$warm",'--output_dir',"$root/runs",'--solution_dir',"$root/solutions",'--fail_on_empty_suite')
    }
    Write-Host "SPBS output: $root" -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'benchmark-sensitivity') {
    $root = Get-CampaignRoot 'sensitivity'
    Run-Python @('cie/code/run_cie_benchmarks.py','--manifest',$Manifest,'--splits','test','--suites','cie_sensitivity','--methods','scip_default','--seeds',$Seeds,'--time_limit',$TimeLimit.ToString(),'--memory_limit_mb',$MemoryLimitMB.ToString(),'--max_instances_per_suite',$MaxInstances.ToString(),'--warm_start','auto','--output_dir',"$root/runs",'--solution_dir',"$root/solutions",'--fail_on_empty_suite')
    Write-Host "Sensitivity output: $root" -ForegroundColor Green
    exit 0
}

if ($Stage -eq 'analyze') {
    Run-Python @('cie/code/analyze_cie_solutions.py','--input_dir',$AnalysisInput,'--output_dir',$AnalysisOutput,'--validate','--fail_on_invalid')
    Run-Python @('cie/code/summarize_cie_benchmarks.py','--input_dir',$AnalysisInput,'--output_dir',$AnalysisOutput,'--reference_method',$ReferenceMethod)
    exit 0
}
