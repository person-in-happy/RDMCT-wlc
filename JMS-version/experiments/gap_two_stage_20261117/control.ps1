param(
    [ValidateSet('Plan','Prepare','Run','Resume','Status','Report')][string]$Action='Plan',
    [double]$RelativeGap=0.05,
    [ValidateRange(1,2)][int]$MaxWorkers=2,
    [switch]$RetryFailed,
    [string[]]$Cells,
    [string]$Campaign='D:\git\git\RDMCT-A3C\JMS-version\results\gap_two_stage_20261117_g05_r1',
    [string]$Python='G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference='Stop'
if ($PSBoundParameters.ContainsKey('RelativeGap') -and $Action -notin @('Plan','Prepare')) {
    throw 'RelativeGap is frozen at Prepare; use a fresh campaign to change it.'
}
if (($RetryFailed -or $Cells -or $PSBoundParameters.ContainsKey('MaxWorkers')) -and $Action -notin @('Run','Resume')) {
    throw 'MaxWorkers, RetryFailed and Cells apply only to Run/Resume.'
}
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$gapProjectRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..\..')).Path
Push-Location -LiteralPath $gapProjectRoot
try {
    $gapArgs=@('-X','utf8','-u',(Join-Path $PSScriptRoot 'gap_two_stage.py'),$Action.ToLower(),'--campaign',$Campaign)
    if ($Action -in @('Plan','Prepare')) {
        $gapArgs+=@('--relative-gap',$RelativeGap.ToString('G17',[System.Globalization.CultureInfo]::InvariantCulture))
    }
    if ($Action -in @('Run','Resume')) {
        $gapArgs+=@('--max-workers',$MaxWorkers.ToString())
        if ($RetryFailed) { $gapArgs+='--retry-failed' }
        if ($Cells) { $gapArgs+='--cells'; $gapArgs+=$Cells }
    }
    # Keep the supervisor in this visible foreground terminal. Its workers log
    # separately; the foreground shows progress, failures, RAM and an ETA.
    & $Python @gapArgs
    if ($LASTEXITCODE -ne 0) { throw "Gap experiment command failed: $LASTEXITCODE" }
}
finally { Pop-Location }
