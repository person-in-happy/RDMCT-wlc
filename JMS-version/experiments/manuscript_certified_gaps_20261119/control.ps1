param([ValidateSet('Run','Resume','Status')][string]$Action='Run')
$ErrorActionPreference='Stop'
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$gapAction=if ($Action -eq 'Status') {'status'} else {'run'}
Push-Location -LiteralPath (Join-Path $PSScriptRoot '..\..\..')
try {
    & 'G:\conda\envs\a3cenv\python.exe' -B -X utf8 -u (Join-Path $PSScriptRoot 'campaign.py') $gapAction
    $gapCode=$LASTEXITCODE
} finally { Pop-Location }
exit $gapCode
