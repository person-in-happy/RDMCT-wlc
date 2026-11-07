$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
Set-Location -LiteralPath $projectRoot
$logPath = Join-Path $projectRoot 'JMS-version/revisions/20261027_model4/export_console.log'
$statusPath = Join-Path $projectRoot 'JMS-version/revisions/20261027_model4/export_status.json'
Write-Host 'Model4 Pjob export: concurrency=1, GPU=0; existing model2 campaign is unchanged.'
& 'G:\conda\envs\a3cenv\python.exe' -X utf8 -u JMS-version/tools/model4_feasible_orders.py 2>&1 | Tee-Object -FilePath $logPath
$exportExit = $LASTEXITCODE
@{ exit_code=$exportExit; completed=($exportExit -eq 0) } | ConvertTo-Json | Set-Content -LiteralPath $statusPath -Encoding UTF8
if ($exportExit -ne 0) { throw "Model4 export failed: $exportExit" }
Write-Host 'Model4 export completed. The manifest contains counts and validation evidence.'
