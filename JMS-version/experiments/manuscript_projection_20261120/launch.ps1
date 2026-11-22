param([ValidateSet('scale','campaign')][string]$Task = 'campaign')
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:OPENBLAS_NUM_THREADS = '1'
$env:OMP_NUM_THREADS = '1'
$env:MKL_NUM_THREADS = '1'
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$Host.UI.RawUI.WindowTitle = "Manuscript experiment | $Task"
$workRoot = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
Set-Location -LiteralPath $workRoot
$resultDir = Join-Path $workRoot 'JMS-version/results/manuscript_projection_20261120_r1'
[void](New-Item -ItemType Directory -Force -Path $resultDir)
$logName = "$Task-$(Get-Date -Format yyyyMMdd-HHmmss).log"
Start-Transcript -Path (Join-Path $resultDir $logName) | Out-Null
try {
    & 'G:\conda\python.exe' -B -X utf8 -u (Join-Path $PSScriptRoot "$Task.py")
    $code = $LASTEXITCODE
} finally {
    Stop-Transcript | Out-Null
}
exit $code
