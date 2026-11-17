$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ThesisParallelRoot = 'D:\git\git\RDMCT-A3C'
$ThesisParallelPython = 'G:\conda\envs\a3cenv\python.exe'
$ThesisParallelCampaign = Join-Path $ThesisParallelRoot 'JMS-version\results\thesis_parallel_20261116_r1'
Set-Location -LiteralPath $ThesisParallelRoot
$Host.UI.RawUI.WindowTitle = '硕士论文并行实验：长链见证与节拍消融（最多4路）'
Start-Transcript -Path (Join-Path $ThesisParallelCampaign ('foreground_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log'))
try {
    & $ThesisParallelPython -X utf8 -u (Join-Path $PSScriptRoot 'queue.py') run --queue $ThesisParallelCampaign
    if ($LASTEXITCODE -ne 0) { throw "Parallel supervisor exited: $LASTEXITCODE" }
} finally {
    Stop-Transcript
}
