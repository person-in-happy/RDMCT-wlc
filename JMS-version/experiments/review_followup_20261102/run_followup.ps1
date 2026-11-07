param(
    [ValidateSet('timing','parallel','exact','residency')][string]$Suite='timing',
    [ValidateSet('plan','prepare','start','resume','status')][string]$Action='start',
    [string]$Campaign='',
    [int]$Repeats=6,
    [double]$TimeLimit=0,
    [double]$Stage2Limit=60,
    [int]$MemoryMB=0,
    [int]$ProcessMemoryMB=0,
    [double]$WallLimit=1800,
    [switch]$RetryFailed
)
$ErrorActionPreference='Stop'
$rootPath=Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Set-Location -LiteralPath $rootPath
if ($Action -in @('resume','status')) {
    foreach ($setting in @('Suite','Repeats','TimeLimit','Stage2Limit','MemoryMB','ProcessMemoryMB','WallLimit')) {
        if ($PSBoundParameters.ContainsKey($setting)) { throw "$setting is frozen; use a new campaign to change it." }
    }
    if (-not $Campaign) { throw 'Specify -Campaign for resume/status.' }
} elseif ($RetryFailed) { throw 'Use -RetryFailed only with -Action resume.' }
if (-not $Campaign -and $Action -ne 'plan') {
    $tag=Get-Date -Format 'yyyyMMdd_HHmmss'
    $Campaign="JMS-version/results/review_followup_${Suite}_$tag"
}
$arguments=@('-X','utf8','-u',(Join-Path $PSScriptRoot 'followup.py'),$Action)
if ($Action -notin @('resume','status')) {
    $arguments+=@('--suite',$Suite,'--repeats',"$Repeats",'--stage2-limit',"$Stage2Limit",'--wall-limit',"$WallLimit")
    if ($TimeLimit -gt 0) { $arguments+=@('--time-limit',"$TimeLimit") }
    if ($MemoryMB -gt 0) { $arguments+=@('--memory-mb',"$MemoryMB") }
    if ($ProcessMemoryMB -gt 0) { $arguments+=@('--process-memory-mb',"$ProcessMemoryMB") }
}
if ($Campaign) { $arguments+=@('--campaign',$Campaign) }
if ($RetryFailed) { $arguments+='--retry-failed' }
if ($Action -in @('resume','status')) { Write-Host "Review follow-up $Action | campaign=$Campaign | using frozen settings" }
else { Write-Host "Review follow-up $Action | suite=$Suite | campaign=$Campaign" }
& 'G:\conda\envs\a3cenv\python.exe' @arguments
if ($LASTEXITCODE -ne 0) { throw "Review follow-up stopped (exit $LASTEXITCODE). Inspect the saved summary and logs." }
