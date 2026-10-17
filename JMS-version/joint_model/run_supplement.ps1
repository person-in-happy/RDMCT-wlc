param(
    [ValidateSet('reference','model','algorithm','crossover')][string]$Suite='model',
    [string]$OutputDir='',
    [switch]$Resume,
    [switch]$PrepareOnly,
    [double]$TimeLimit=480,
    [double]$Stage2Limit=120,
    [double]$InitializationBudget=60,
    [double]$MemoryMB=20000,
    [string]$Python='G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference='Stop'
$RepoRoot=Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location -LiteralPath $RepoRoot
$Runner=Join-Path $PSScriptRoot 'run_experiments.py'
if (-not $OutputDir) {
    if ($Resume) { throw 'Resume requires the existing OutputDir.' }
    $OutputDir=Join-Path $RepoRoot ('JMS-version\results\joint_experiments\'+$Suite+'_'+(Get-Date -Format 'yyyyMMdd_HHmmss'))
}
if (-not $Resume) {
    $PrepareArgs=@($Runner,'prepare','--output',$OutputDir)
    switch ($Suite) {
        reference { $PrepareArgs+=@('--suite','reference','--seeds','1') }
        model { $PrepareArgs+=@('--suite','comparison','--formulations','joint','fixed') }
        algorithm { $PrepareArgs+=@('--suite','comparison','--sources','dual','--methods','scip','hem','proposed') }
        crossover { $PrepareArgs+=@('--suite','crossover','--sources','dual','--seeds','1','--methods','proposed') }
    }
    & $Python @PrepareArgs
    if ($LASTEXITCODE -ne 0) { throw 'Campaign preparation failed.' }
}
Write-Host "Campaign: $OutputDir"
if ($PrepareOnly) { return }
$RunArgs=@($Runner,'run','--campaign',$OutputDir,'--time-limit',"$TimeLimit",'--stage2-limit',"$Stage2Limit",'--initialization-budget',"$InitializationBudget",'--memory-mb',"$MemoryMB")
if ($Resume) { $RunArgs+='--resume' }
& $Python @RunArgs
if ($LASTEXITCODE -ne 0) { throw 'Run stopped. Saved results remain in the campaign directory.' }
& $Python (Join-Path $PSScriptRoot 'summarize.py') --campaign $OutputDir
if ($LASTEXITCODE -ne 0) { throw 'Independent summary failed.' }
