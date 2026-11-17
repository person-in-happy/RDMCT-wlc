param(
    [ValidateSet('Run','Resume','Stop','Status')][string]$Action='Run',
    [string]$Campaign='D:\git\git\RDMCT-A3C\JMS-version\results\s1_ablation_20261117_r1'
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Set-Location -LiteralPath 'D:\git\git\RDMCT-A3C'
$Host.UI.RawUI.WindowTitle='S1 supplement: completed / 144, failed, remaining time'
$s1Action = if ($Action -eq 'Resume') {'run'} else {$Action.ToLower()}
Start-Transcript -Path (Join-Path $Campaign ('foreground_' + $s1Action + '_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log'))
try {
    & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u (Join-Path $PSScriptRoot 's1_ablation.py') $s1Action --campaign $Campaign
    if ($LASTEXITCODE -ne 0) { throw "S1 supplement exited with code $LASTEXITCODE" }
}
finally { Stop-Transcript }
