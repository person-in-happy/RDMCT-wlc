param(
    [ValidateSet('Plan','Prepare','Run','Resume','Stop','Status','Report')][string]$Action='Plan',
    [double[]]$Weights=@(0.0001,0.0005,0.001,10,100),
    [string]$Campaign='D:\git\git\RDMCT-A3C\JMS-version\results\joint_weight_sensitivity_20261117_r1'
)
$ErrorActionPreference='Stop'
if ($PSBoundParameters.ContainsKey('Weights') -and $Action -notin @('Plan','Prepare')) {
    throw 'Weights can only be specified for Plan/Prepare; Run/Resume use the frozen weights.'
}
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Set-Location -LiteralPath 'D:\git\git\RDMCT-A3C'
$sensitivityArgs=@('-X','utf8','-u',(Join-Path $PSScriptRoot 'sensitivity.py'),$Action.ToLower(),'--campaign',$Campaign)
if ($Action -in @('Plan','Prepare')) {
    $sensitivityArgs+='--weights'
    $sensitivityArgs+=@($Weights | ForEach-Object { $_.ToString('G17',[System.Globalization.CultureInfo]::InvariantCulture) })
}
$sensitivityTranscript=$Action -in @('Run','Resume')
if ($sensitivityTranscript) {
    $Host.UI.RawUI.WindowTitle='Table 4 weight sensitivity: completed / failed / remaining time'
    Start-Transcript -Path (Join-Path $Campaign ('foreground_' + $Action.ToLower() + '_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log'))
}
try {
    & 'G:\conda\envs\a3cenv\python.exe' @sensitivityArgs
    if ($LASTEXITCODE -ne 0) { throw "Weight sensitivity command failed: $LASTEXITCODE" }
}
finally { if ($sensitivityTranscript) { Stop-Transcript } }
