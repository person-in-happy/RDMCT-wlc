param(
    [ValidateSet('Plan','Prepare','Run','Resume','Status','Report')][string]$Action='Plan',
    [double[]]$Gaps=@(0.05,0.01,0.10),
    [double]$SecondarySeconds=300,
    [double]$PrimarySeconds=0,
    [ValidateRange(1,2)][int]$MaxWorkers=2,
    [switch]$RetryFailed,
    [string[]]$Cells,
    [string]$Campaign='D:\git\git\RDMCT-A3C\JMS-version\results\gap_post_switch_20261118_r1',
    [string]$Python='G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference='Stop'
foreach ($gapSetting in @('Gaps','SecondarySeconds','PrimarySeconds')) {
    if ($PSBoundParameters.ContainsKey($gapSetting) -and $Action -notin @('Plan','Prepare')) {
        throw "$gapSetting is frozen at Prepare; use a new campaign to change it."
    }
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
        $gapArgs+='--gaps'
        foreach ($gapValue in $Gaps) {
            $gapArgs+=$gapValue.ToString('G17',[System.Globalization.CultureInfo]::InvariantCulture)
        }
        $gapArgs+=@('--secondary-seconds',$SecondarySeconds.ToString('G17',[System.Globalization.CultureInfo]::InvariantCulture))
        $gapArgs+=@('--primary-seconds',$PrimarySeconds.ToString('G17',[System.Globalization.CultureInfo]::InvariantCulture))
    }
    if ($Action -in @('Run','Resume')) {
        $gapArgs+=@('--max-workers',$MaxWorkers.ToString())
        if ($RetryFailed) { $gapArgs+='--retry-failed' }
        if ($Cells) { $gapArgs+='--cells'; $gapArgs+=$Cells }
    }
    # This process remains in the user's visible foreground terminal.
    & $Python @gapArgs
    if ($LASTEXITCODE -ne 0) { throw "Gap experiment command failed: $LASTEXITCODE" }
}
finally { Pop-Location }
