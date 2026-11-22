param([Parameter(Mandatory)][string]$Campaign)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$Host.UI.RawUI.WindowTitle = "Full-model Pareto audit | $Campaign"
$experimentRoot = (Resolve-Path -LiteralPath (Join-Path (Join-Path $PSScriptRoot 'runs') $Campaign)).Path
$experimentPython = 'G:\conda\envs\a3cenv\python.exe'
Start-Transcript -Path (Join-Path $experimentRoot ("evaluation_{0}.log" -f (Get-Date -Format 'yyyyMMdd_HHmmss')))
try {
    while (-not (Test-Path -LiteralPath (Join-Path $experimentRoot 'finished.json'))) {
        Start-Sleep -Seconds 10
    }
    & $experimentPython -B -X utf8 -u (Join-Path $PSScriptRoot 'recovery.py') $experimentRoot
    if ($LASTEXITCODE -ne 0) { throw 'Recovery failed. See the worker log.' }
    & $experimentPython -B -X utf8 -u (Join-Path $PSScriptRoot 'evaluate.py') $experimentRoot
    if ($LASTEXITCODE -ne 0) { throw 'Audit or plotting failed. See this transcript.' }
} finally {
    Stop-Transcript
}
