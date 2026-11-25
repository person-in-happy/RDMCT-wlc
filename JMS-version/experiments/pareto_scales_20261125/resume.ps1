param([Parameter(Mandatory=$true)][ValidateSet('four_slow','sixteen_810','sixteen_817')][string]$CaseName)
$ErrorActionPreference = 'Stop'
& 'G:/conda/python.exe' -B -u -X utf8 (Join-Path $PSScriptRoot 'sweep.py') $CaseName
exit $LASTEXITCODE
