param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('validation','main','stability','doe','spbs','sensitivity','ood')]
    [string]$Stage,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_-]+$')]
    [string]$CampaignId,
    [ValidatePattern('^[0-9, ]*$')]
    [string]$SolverSeeds = '',
    [ValidatePattern('^[0-9, ]*$')]
    [string]$TrainingSeeds = '1,2,3,4,5',
    [ValidateSet('both','none','auto')]
    [string]$SpbsWarmStarts = 'both',
    [string]$Reference = '',
    [ValidateRange(1,1000000)]
    [int]$BootstrapSamples = 2000,
    [int]$BootstrapSeed = 2027,
    [switch]$NoPlots
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path $PSScriptRoot -Parent
Set-Location $RepoRoot

$defaultSeeds = @{
    validation = '1'
    main = '1,2,3,4,5'
    stability = '1,2,3,4,5'
    doe = '1,2,3,4,5'
    spbs = '1,2,3,4,5,6,7,8,9,10'
    sensitivity = '1,2,3,4,5,6,7,8,9,10'
    ood = '1,2,3'
}
$defaultReferences = @{
    validation = 'scip_default'
    main = 'proposed'
    stability = 'proposed[full]'
    doe = 'scip_default[manufacturing_doe]'
    spbs = 'scip_default[spbs_auto]'
    sensitivity = 'scip_default'
    ood = 'proposed'
}
if ([string]::IsNullOrWhiteSpace($SolverSeeds)) { $SolverSeeds = $defaultSeeds[$Stage] }
if ([string]::IsNullOrWhiteSpace($Reference)) { $Reference = $defaultReferences[$Stage] }

$campaignRoot = Join-Path $RepoRoot "cie\results\$Stage\$CampaignId"
if (-not (Test-Path -LiteralPath $campaignRoot -PathType Container)) {
    throw "Campaign directory does not exist: $campaignRoot"
}
$combined = Join-Path $campaignRoot 'combined'
$validationAnalysis = Join-Path $campaignRoot 'analysis'
$submissionAnalysis = Join-Path $campaignRoot 'submission_analysis'
New-Item -ItemType Directory -Force -Path $combined,$validationAnalysis,$submissionAnalysis | Out-Null

function Run-Python {
    param([string[]]$Arguments)
    Write-Host "> python $($Arguments -join ' ')" -ForegroundColor Cyan
    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python failed with exit code $LASTEXITCODE"
    }
}

Run-Python @(
    'cie/code/combine_cie_runs.py',
    '--input_dir', $campaignRoot,
    '--output_dir', $combined,
    '--recursive'
)
Run-Python @(
    'cie/code/analyze_cie_solutions.py',
    '--input_dir', $campaignRoot,
    '--output_dir', $validationAnalysis,
    '--validate',
    '--fail_on_invalid'
)
Run-Python @(
    'cie/code/audit_cie_submission.py',
    '--stage', $Stage,
    '--input-dir', $campaignRoot,
    '--analysis-dir', $validationAnalysis,
    '--solver-seeds', $SolverSeeds,
    '--training-seeds', $TrainingSeeds,
    '--spbs-warm-starts', $SpbsWarmStarts,
    '--json-report', (Join-Path $submissionAnalysis 'submission_audit.json')
)
$analysisArgs = @(
    'cie/code/analyze_cie_submission.py',
    '--input_dir', $campaignRoot,
    '--output_dir', $submissionAnalysis,
    '--stage', $Stage,
    '--reference', $Reference,
    '--bootstrap_samples', $BootstrapSamples.ToString(),
    '--bootstrap_seed', $BootstrapSeed.ToString()
)
if ($NoPlots) { $analysisArgs += '--no_plots' }
Run-Python $analysisArgs

if ($Stage -eq 'doe' -and -not $NoPlots) {
    foreach ($name in @('cie_submission_doe_pdi_effects.png','cie_submission_doe_diagnostics.png')) {
        $figure = Join-Path $submissionAnalysis $name
        if (-not (Test-Path -LiteralPath $figure -PathType Leaf)) {
            throw "DOE figure was not generated: $figure. Install requirements.txt before the formal freeze."
        }
    }
}

Write-Host "C&IE post-processing PASS: $Stage / $CampaignId" -ForegroundColor Green
Write-Host "Validated solutions: $validationAnalysis" -ForegroundColor DarkGray
Write-Host "Submission analysis: $submissionAnalysis" -ForegroundColor DarkGray
