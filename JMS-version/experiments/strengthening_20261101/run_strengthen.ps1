param(
    [ValidateSet('rhythm_memory','representation')][string]$Suite='rhythm_memory',
    [ValidateSet('plan','prepare','start','resume','status')][string]$Action='start',
    [string]$Campaign='',
    [int[]]$Seeds=@(1,2,3),
    [int]$MemoryMB=10000,
    [int]$ProcessMemoryMB=14000,
    [double]$TimeLimit=300,
    [double]$Stage2Limit=60,
    [double]$WallLimit=3600,
    [switch]$RetryFailed
)
$ErrorActionPreference='Stop'
$rootPath=Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Set-Location -LiteralPath $rootPath
if ($Action -in @('resume','status')) {
    foreach ($setting in @('Suite','Seeds','MemoryMB','ProcessMemoryMB','TimeLimit','Stage2Limit','WallLimit')) {
        if ($PSBoundParameters.ContainsKey($setting)) { throw "$setting is frozen; use a new campaign to change it." }
    }
    if (-not $Campaign) { throw 'Specify -Campaign for resume/status.' }
} elseif ($RetryFailed) { throw 'Use -RetryFailed only with -Action resume.' }
if (-not $Campaign -and $Action -ne 'plan') {
    $tag=Get-Date -Format 'yyyyMMdd_HHmmss'
    $Campaign="JMS-version/results/strengthen_${Suite}_$tag"
}
$arguments=@('-X','utf8','-u',(Join-Path $PSScriptRoot 'strengthen.py'),$Action)
if ($Action -notin @('resume','status')) {
    $arguments+=@('--suite',$Suite,'--memory-mb',"$MemoryMB",'--process-memory-mb',"$ProcessMemoryMB",'--time-limit',"$TimeLimit",'--stage2-limit',"$Stage2Limit",'--wall-limit',"$WallLimit",'--seeds')+$Seeds.ForEach({"$_"})
}
if ($Campaign) { $arguments+=@('--campaign',$Campaign) }
if ($RetryFailed) { $arguments+='--retry-failed' }
if ($Action -in @('resume','status')) { Write-Host "Strengthening $Action | campaign=$Campaign | using frozen settings" }
else { Write-Host "Strengthening $Action | suite=$Suite | campaign=$Campaign" }
& 'G:\conda\envs\a3cenv\python.exe' @arguments
if ($LASTEXITCODE -ne 0) { throw "Strengthening command stopped (exit $LASTEXITCODE). Inspect saved logs and coverage." }
