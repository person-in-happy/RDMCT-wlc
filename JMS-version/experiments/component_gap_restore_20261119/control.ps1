param()
$ErrorActionPreference='Stop'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
Push-Location -LiteralPath (Join-Path $PSScriptRoot '..\..\..')
try {
    & 'G:\conda\envs\a3cenv\python.exe' -B -X utf8 -u (Join-Path $PSScriptRoot 'campaign.py')
    $code=$LASTEXITCODE
} finally { Pop-Location }
exit $code
