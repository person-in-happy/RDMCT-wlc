param(
    [ValidateSet('baseline','rhythm','cleanup')][string]$Suite='baseline',
    [ValidateSet('plan','prepare','start','resume','status')][string]$Action='start',
    [string]$Campaign='',
    [string]$PaperCampaign='',
    [string]$QualificationCampaign='',
    [string]$RhythmCampaign='',
    [int[]]$Seeds=@(1,2,3),
    [int]$MemoryMB=10000,
    [int]$ProcessMemoryMB=14000,
    [double]$TimeLimit=300,
    [double]$Stage2Limit=60,
    [double]$CleanupLimit=60,
    [double]$WallLimit=3600,
    [switch]$RetryFailed
)
$ErrorActionPreference='Stop'
$rootPath=Split-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) -Parent
Set-Location -LiteralPath $rootPath
if ($Action -in @('resume','status')) {
    foreach ($setting in @('PaperCampaign','QualificationCampaign','RhythmCampaign','Suite','Seeds','MemoryMB','ProcessMemoryMB','TimeLimit','Stage2Limit','CleanupLimit','WallLimit')) {
        if ($PSBoundParameters.ContainsKey($setting)) { throw "$setting is frozen; use a new campaign to change it." }
    }
    if (-not $Campaign) { throw 'Specify -Campaign for resume/status.' }
} elseif ($RetryFailed) { throw 'Use -RetryFailed only with -Action resume.' }
if (-not $Campaign -and $Action -ne 'plan') {
    $tag=Get-Date -Format 'yyyyMMdd_HHmmss'
    $Campaign="JMS-version/results/nondecreasing_review_${Suite}_$tag"
}
$arguments=@('-X','utf8','-u',(Join-Path $PSScriptRoot 'review_experiments.py'),$Action)
if ($Action -notin @('resume','status')) {
    $arguments+=@('--suite',$Suite,'--memory-mb',"$MemoryMB",'--process-memory-mb',"$ProcessMemoryMB",'--time-limit',"$TimeLimit",'--stage2-limit',"$Stage2Limit",'--cleanup-limit',"$CleanupLimit",'--wall-limit',"$WallLimit",'--seeds')+$Seeds.ForEach({"$_"})
}
foreach ($source in @(@('paper-campaign',$PaperCampaign),@('qualification-campaign',$QualificationCampaign),@('rhythm-campaign',$RhythmCampaign))) {
    if ($source[1]) { $arguments+=@(("--" + $source[0]),$source[1]) }
}
if ($Campaign) { $arguments+=@('--campaign',$Campaign) }
if ($RetryFailed) { $arguments+='--retry-failed' }
if ($Action -in @('resume','status')) { Write-Host "Review $Action | campaign=$Campaign | using frozen settings" }
else { Write-Host "Review $Action | suite=$Suite | campaign=$Campaign" }
& 'G:\conda\envs\a3cenv\python.exe' @arguments
if ($LASTEXITCODE -ne 0) { throw "Review command stopped (exit $LASTEXITCODE). Inspect saved logs and coverage." }
