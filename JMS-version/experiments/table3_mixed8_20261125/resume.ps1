$ErrorActionPreference = 'Stop'
$pythonExe = 'G:/conda/python.exe'
$campaignDir = $PSScriptRoot
$resultsDir = Join-Path (Split-Path (Split-Path $campaignDir -Parent) -Parent) 'results/table3_mixed8_20261125'
$preparation = Join-Path $campaignDir 'prepare.py'
$controller = Join-Path $campaignDir 'archive.py'
if (-not (Test-Path -LiteralPath (Join-Path $resultsDir 'preparation.json'))) {
    Write-Host 'Eight-wafer SPBS preparation. Historical duration about one minute.'
    & $pythonExe -B -u -X utf8 $preparation
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $pythonExe -B -u -X utf8 $controller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pythonExe -B -u -X utf8 (Join-Path $campaignDir 'verify_archive.py')
exit $LASTEXITCODE
