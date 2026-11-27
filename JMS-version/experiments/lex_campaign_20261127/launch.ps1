param(
    [ValidateSet(1, 2)][int]$Jobs = 2,
    [string]$OutputDirectory = '',
    [string[]]$Cases = @(),
    [switch]$RetryFailed
)
$ErrorActionPreference = 'Stop'
$jmsDir = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$solverPython = Join-Path $jmsDir '.solver_env/Scripts/python.exe'
$runArgs = @('-u', (Join-Path $PSScriptRoot 'runner.py'), 'run', '--jobs', "$Jobs")
if ($OutputDirectory) { $runArgs += @('--output', $OutputDirectory) }
if ($Cases.Count) { $runArgs += '--cases'; $runArgs += $Cases }
if ($RetryFailed) { $runArgs += '--retry-failed' }
& $solverPython @runArgs
exit $LASTEXITCODE
