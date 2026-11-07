param([string]$RunTag = (Get-Date -Format 'yyyyMMdd_HHmmss'))
$ErrorActionPreference='Stop'
$rootPath=Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $rootPath
$validationDir=Join-Path $rootPath "JMS-version/revisions/20261102_nondecreasing_release/validation_$RunTag"
New-Item -ItemType Directory -Path $validationDir -ErrorAction Stop | Out-Null
Write-Host 'Nondecreasing release validation: 10 bounded correctness tests; no formal campaign.'
& 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u -m pytest (Join-Path $PSScriptRoot 'test_nondecreasing.py') -v --tb=short -p no:cacheprovider "--junitxml=$validationDir/tests.xml"
if ($LASTEXITCODE -ne 0) {throw 'Correctness tests failed'}
& 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u (Join-Path $PSScriptRoot 'verify_entries.py')
if ($LASTEXITCODE -ne 0) {throw 'Entry checks failed'}
Write-Host "Validation completed; tests=$validationDir; entry report=$PSScriptRoot/entry_validation.json"
