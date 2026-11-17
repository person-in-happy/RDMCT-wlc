param(
    [string]$Campaign = 'D:\git\git\RDMCT-A3C\JMS-version\results\formal_ablation_20261117_r1'
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$experimentRoot = 'D:\git\git\RDMCT-A3C'
Set-Location -LiteralPath $experimentRoot
$Host.UI.RawUI.WindowTitle = 'Formal finite-budget ablation: completed / failed / ETA'
$transcriptPath = Join-Path $Campaign ('foreground_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log')
Start-Transcript -Path $transcriptPath
try {
    & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u (Join-Path $PSScriptRoot 'formal_ablation.py') run --campaign $Campaign
    if ($LASTEXITCODE -ne 0) { throw "Experiment supervisor exited with code $LASTEXITCODE" }
}
finally {
    Stop-Transcript
}
