param(
    [int]$WaitForProcessId = 0,
    [double]$TimeLimit = 14400,
    [int]$WarmStartTimeLimit = 600,
    [double]$MemoryLimitMB = 4096,
    [string]$RunLabel = 'jms_product_cmax_n8_n16_H4_H9_20260904'
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

# The launcher calls the pinned a3cenv Python executable directly and checks
# this marker before running its CUDA/PySCIPOpt preflight.
$env:CONDA_DEFAULT_ENV = 'a3cenv'

$Parameters = @{
    WaferCounts = '8,16'
    CleaningIntervals = '4-9'
    TrainingSeeds = '1'
    SolverSeeds = '1'
    TimeLimit = $TimeLimit
    WarmStartTimeLimit = $WarmStartTimeLimit
    MemoryLimitMB = $MemoryLimitMB
    ScipVerbosity = 2
    ScipHeuristicsProfile = 'aggressive'
    ScipNonrootSeparationRounds = 0
    RunLabel = $RunLabel
}

$Launcher = Join-Path $PSScriptRoot 'run_mode_cleaning_crossover.ps1'
& $Launcher @Parameters

if ($LASTEXITCODE -ne 0) {
    throw "Product-return Cmax crossover campaign failed with exit code $LASTEXITCODE."
}
