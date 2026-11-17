$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$experimentRoot = 'D:\git\git\RDMCT-A3C'
Set-Location -LiteralPath $experimentRoot
$experimentCampaign = Join-Path $experimentRoot 'JMS-version\results\finite_budget_readiness_20261117_r1'
$Host.UI.RawUI.WindowTitle = 'Ablation readiness: 2 SCIP probes, 900 seconds each'
Start-Transcript -Path (Join-Path $experimentCampaign ('foreground_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log'))
try {
    & 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u (Join-Path $PSScriptRoot 'readiness.py') run --campaign $experimentCampaign
    if ($LASTEXITCODE -ne 0) { throw "Readiness supervisor exited: $LASTEXITCODE" }
} finally {
    Stop-Transcript
}
