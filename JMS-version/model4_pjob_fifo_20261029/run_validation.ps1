param([string]$RunTag = (Get-Date -Format 'yyyyMMdd_HHmmss'),[string]$TestFilter='')
$ErrorActionPreference = 'Stop'
$rootPath = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location -LiteralPath $rootPath
$validationDir = Join-Path $rootPath "JMS-version/revisions/20261029_pjob_index_encoding/backend_validation_$RunTag"
New-Item -ItemType Directory -Path $validationDir -ErrorAction Stop | Out-Null
Write-Host 'Model4 validation: foreground, 1 CPU worker, no GPU policy jobs; short solver checks only.'
$pytestArguments=@('-X','utf8','-u','-m','pytest',(Join-Path $PSScriptRoot 'test_model4.py'),(Join-Path $PSScriptRoot 'test_pjob_order.py'),'-v','--tb=short',"--junitxml=$validationDir/tests.xml")
if ($TestFilter) { $pytestArguments+=@('-k',$TestFilter) }
& 'G:\conda\envs\a3cenv\python.exe' @pytestArguments 2>&1 | Tee-Object -FilePath (Join-Path $validationDir 'console.log')
$validationCode = $LASTEXITCODE
@{exit_code=$validationCode;completed=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $validationDir 'status.json') -Encoding UTF8
Write-Host "Validation finished: exit=$validationCode; report=$validationDir"
