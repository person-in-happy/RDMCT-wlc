param(
    [ValidateSet('Resume', 'Stop', 'Status')]
    [string]$Action = 'Resume',
    [string]$Campaign = 'D:\git\git\RDMCT-A3C\JMS-version\results\formal_ablation_20261117_r1'
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location -LiteralPath 'D:\git\git\RDMCT-A3C'
if ($Action -eq 'Resume') {
    $Host.UI.RawUI.WindowTitle = 'Resuming formal ablation: completed / failed / ETA'
}
$resumeTranscript = Join-Path $Campaign ('resume_' + $Action.ToLower() + '_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')
Start-Transcript -Path $resumeTranscript
try {
    & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u (Join-Path $PSScriptRoot 'resume.py') $Action.ToLower() --campaign $Campaign
    if ($LASTEXITCODE -ne 0) { throw "Campaign control exited with code $LASTEXITCODE" }
}
finally {
    Stop-Transcript
}
