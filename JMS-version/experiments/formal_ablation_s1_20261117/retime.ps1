param([string]$Campaign='D:\git\git\RDMCT-A3C\JMS-version\results\s1_retiming_20261117_r1')
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
Set-Location -LiteralPath 'D:\git\git\RDMCT-A3C'
$Host.UI.RawUI.WindowTitle='S1 mixed initial schedule: material-flow retiming'
Start-Transcript -Path (Join-Path $Campaign ('foreground_'+(Get-Date -Format 'yyyyMMdd_HHmmss')+'.log'))
try {
    & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u (Join-Path $PSScriptRoot 'retime_s1.py') run --campaign $Campaign
    if ($LASTEXITCODE -ne 0) { throw "S1 retiming exited with code $LASTEXITCODE" }
}
finally { Stop-Transcript }
