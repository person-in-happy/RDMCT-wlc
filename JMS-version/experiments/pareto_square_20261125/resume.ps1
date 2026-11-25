param([string]$Python = "G:/conda/python.exe")
$ErrorActionPreference = "Stop"

function Invoke-Stage([string]$Source, [string[]]$StageArgs) {
    $scriptFile = Join-Path $PSScriptRoot $Source
    Write-Host "Starting $Source $StageArgs"
    & $Python -B -u -X utf8 $scriptFile @StageArgs
    if ($LASTEXITCODE -ne 0) { throw "$Source exited with status $LASTEXITCODE" }
}

Invoke-Stage "support.py" @("--budget", "80")
Invoke-Stage "fixed.py" @("all")
Invoke-Stage "search.py" @("--budget", "30")
Invoke-Stage "eight_tail.py" @()
Invoke-Stage "certify.py" @()
Invoke-Stage "native.py" @()
Invoke-Stage "bridge.py" @()
Invoke-Stage "refine.py" @()
Invoke-Stage "guided.py" @()
Invoke-Stage "native.py" @()
Invoke-Stage "publish.py" @()
