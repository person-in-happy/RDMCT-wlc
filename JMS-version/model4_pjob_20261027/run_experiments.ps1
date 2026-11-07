param(
    [ValidateSet('smoke','core','crossover','ablation','sensitivity','scale','diagnostic','fixed','mode24','scale32','gantt16','rhythm','cleaning','doe','ood')]
    [string]$Suite='core',
    [ValidateSet('all','three_classes','lp_split')][string]$Qualification='all',
    [ValidateSet('start','prepare','preflight','run','resume','audit','status')][string]$Action='start',
    [string]$Campaign='',
    [int]$Jobs=2,
    [int]$MemoryMB=6000,
    [int]$ProcessMemoryMB=7000,
    [double]$TimeLimit=0,
    [double]$WallLimit=0,
    [double]$SpbsBudget=-1,
    [int[]]$Seeds=@(),
    [ValidateSet('root_only','standard')][string]$CutProfile='root_only'
)
$ErrorActionPreference='Stop'
if ($Action -notin @('start','prepare')) {
    foreach ($setting in @('Suite','Qualification','Jobs','MemoryMB','ProcessMemoryMB','TimeLimit','WallLimit','SpbsBudget','Seeds','CutProfile')) {
        if ($PSBoundParameters.ContainsKey($setting)) { throw "$setting is frozen; use a new start/prepare batch to change it." }
    }
}
$rootPath=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $rootPath
if (-not $Campaign) {
    if ($Action -notin @('start','prepare')) { throw 'Specify -Campaign for a frozen existing batch.' }
    $tag=Get-Date -Format 'yyyyMMdd_HHmmss'
    $Campaign="JMS-version/results/model4_${Suite}_${Qualification}_$tag"
}
$runner=Join-Path $PSScriptRoot 'evidence_supplement.py'
$arguments=@('-X','utf8','-u',$runner,$Action,'--campaign',$Campaign)
if ($Action -in @('start','prepare')) {
    $arguments+=@('--suite',$Suite,'--qualification',$Qualification,'--jobs',"$Jobs",'--memory-mb',"$MemoryMB",'--process-memory-mb',"$ProcessMemoryMB",'--cut-profile',$CutProfile)
    if ($TimeLimit -gt 0) { $arguments+=@('--time-limit',"$TimeLimit") }
    if ($WallLimit -gt 0) { $arguments+=@('--wall-limit',"$WallLimit") }
    if ($SpbsBudget -ge 0) { $arguments+=@('--spbs-budget',"$SpbsBudget") }
    if ($Seeds.Count -gt 0) { $arguments+=@('--seeds')+$Seeds.ForEach({"$_"}) }
}
if ($Action -in @('start','prepare')) { Write-Host "Model4 $Action | suite=$Suite | campaign=$Campaign" }
else { Write-Host "Model4 $Action | campaign=$Campaign | using frozen settings" }
& 'G:\conda\envs\a3cenv\python.exe' @arguments
if ($LASTEXITCODE -ne 0) { throw "Model4 command stopped (exit $LASTEXITCODE). Inspect the saved report; no old campaign was replaced." }
