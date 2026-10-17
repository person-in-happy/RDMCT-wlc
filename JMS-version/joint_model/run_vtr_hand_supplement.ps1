param(
    [ValidateSet('routes','matched','grid','sensitivity','all')][string]$Stage='routes',
    [string]$OutputRoot='',
    [string]$Python='G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference='Stop'
$Repo=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $Repo
if (-not $OutputRoot) { $OutputRoot=Join-Path $Repo ('JMS-version\results\joint_model\vtr_clean_dirty_'+(Get-Date -Format 'yyyyMMdd_HHmmss')) }
if (-not [IO.Path]::IsPathRooted($OutputRoot)) { $OutputRoot=Join-Path $Repo $OutputRoot }
$OutputRoot=[IO.Path]::GetFullPath($OutputRoot)
New-Item -ItemType Directory -Path $OutputRoot -Force | Out-Null
$Runner=Join-Path $PSScriptRoot 'run_experiments.py'
function Invoke-Py([string[]]$Arguments) {
    & $Python @Arguments | Out-Host
    if ($LASTEXITCODE -ne 0) { throw ('Experiment stopped; saved outputs retained: '+($Arguments -join ' ')) }
}
function Prepare-Campaign([string]$Name,[string[]]$Options) {
    $Dest=Join-Path $OutputRoot $Name
    if (-not (Test-Path (Join-Path $Dest 'campaign.json'))) {
        Invoke-Py (@($Runner,'prepare','--output',$Dest)+$Options)
    }
    return $Dest
}
if ($Stage -in @('routes','all')) {
    $Dest=Prepare-Campaign 'routes' @('--suite','reference','--sizes','2','4','--thresholds','2','3','--recipes','mixed','--sources','single','dual','--seeds','1','--methods','scip','--formulations','joint')
    Invoke-Py @($Runner,'run','--campaign',$Dest,'--resume','--time-limit','120','--stage2-limit','0','--initialization','spbs','--initialization-budget','20')
}
if ($Stage -in @('matched','all')) {
    $Specifications=@(@(6,3,'single'),@(6,3,'dual'),@(8,3,'dual'),@(8,10,'dual'),@(16,3,'dual'),@(24,3,'dual'))
    foreach ($Spec in $Specifications) {
        $N=[string]$Spec[0];$H=[string]$Spec[1];$Source=[string]$Spec[2];$Id='n'+$N+'_H'+$H+'_'+$Source
        $Prep=Prepare-Campaign ('inputs_'+$Id) @('--suite','comparison','--sizes',$N,'--thresholds',$H,'--recipes','mixed','--sources',$Source,'--seeds','1','--methods','scip','--formulations','joint')
        $Config=Join-Path $Prep ('configs\n'+$N+'_H'+$H+'_mixed_'+$Source+'.json')
        $Common=Join-Path $OutputRoot ('common_'+$Id)
        if (-not (Test-Path (Join-Path $Common 'certificate.json'))) {
            Invoke-Py @((Join-Path $PSScriptRoot 'supplement_protocol.py'),'--config',$Config,'--output',$Common)
        }
        foreach ($Part in @('structure','algorithm','refinement')) {
            Invoke-Py @((Join-Path $PSScriptRoot 'run_matched_supplement.py'),'--reference',$Common,'--output',(Join-Path $OutputRoot ('matched_'+$Id)),'--stage',$Part,'--time-limit','300','--resume')
        }
    }
}
if ($Stage -in @('grid','all')) {
    $Dest=Prepare-Campaign 'grid' @('--suite','crossover','--sizes','8','16','24','--thresholds','3','4','5','6','7','8','9','10','--recipes','4x1','2x2','mixed','--sources','dual','--seeds','1','--methods','scip','--formulations','joint')
    Invoke-Py @($Runner,'run','--campaign',$Dest,'--resume','--time-limit','300','--stage2-limit','0','--initialization','spbs','--initialization-budget','20')
}
if ($Stage -in @('sensitivity','all')) {
    Invoke-Py @((Join-Path $PSScriptRoot 'vtr_sensitivity.py'),'--output',(Join-Path $OutputRoot 'sensitivity'))
}
Write-Host ('Saved campaign root: '+$OutputRoot)

