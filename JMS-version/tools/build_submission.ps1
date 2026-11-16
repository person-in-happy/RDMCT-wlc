param([string]$Python = 'G:\conda\python.exe', [switch]$RenderDocx)
$ErrorActionPreference = 'Stop'
$buildArguments = @('-X', 'utf8', (Join-Path $PSScriptRoot 'build_submission_en.py'))
if ($RenderDocx) { $buildArguments += '--render-docx' }
& $Python @buildArguments
if ($LASTEXITCODE -ne 0) { throw 'Submission build failed; diagnostics retained in output/.build_en.' }
