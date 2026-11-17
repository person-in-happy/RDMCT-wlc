param([switch]$CheckOnly)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ResumeRoot = 'D:\git\git\RDMCT-A3C'
$ResumePython = 'G:\conda\envs\a3cenv\python.exe'
Set-Location -LiteralPath $ResumeRoot
$Host.UI.RawUI.WindowTitle = 'Thesis experiments: safe resume'
$ResumeAction = if ($CheckOnly) { 'inspect' } else { 'run' }
& $ResumePython -X utf8 -u (Join-Path $PSScriptRoot 'resume.py') $ResumeAction
if ($LASTEXITCODE -ne 0) { throw "Resume exited: $LASTEXITCODE. Preserve logs and interrupted attempts." }
