$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "JMS 16-wafer ablations - two gap stops"
Set-Location -LiteralPath (Resolve-Path (Join-Path $PSScriptRoot "../../.."))
$env:OMP_NUM_THREADS = "1"
$env:MKL_NUM_THREADS = "1"
$env:OPENBLAS_NUM_THREADS = "1"
& G:\conda\envs\a3cenv\python.exe -B -X utf8 -u (Join-Path $PSScriptRoot "campaign.py")
exit $LASTEXITCODE
