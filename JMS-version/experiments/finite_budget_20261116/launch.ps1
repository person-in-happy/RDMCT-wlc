$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$experimentRoot = 'D:\git\git\RDMCT-A3C'
Set-Location -LiteralPath $experimentRoot
$experimentPython = 'G:\conda\envs\a3cenv\python.exe'
$experimentEntry = Join-Path $PSScriptRoot 'finite_budget.py'
$experimentCampaign = Join-Path $experimentRoot 'JMS-version\results\finite_budget_20261116_r1'
$Host.UI.RawUI.WindowTitle = '论文补充实验：联合目标、两阶段与选割消融'
Start-Transcript -Path (Join-Path $experimentCampaign ('foreground_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log'))
try {
    & $experimentPython -X utf8 -u $experimentEntry run --campaign $experimentCampaign
    if ($LASTEXITCODE -ne 0) { throw "Experiment supervisor exited: $LASTEXITCODE" }
} finally {
    Stop-Transcript
}
