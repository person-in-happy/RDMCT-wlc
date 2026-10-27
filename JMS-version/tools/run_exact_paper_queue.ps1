[CmdletBinding()]
param(
    [string]$Output = 'JMS-version/results/paper_cpsat_optimality_20261022',
    [int]$Jobs = 2,
    [int]$Workers = 2,
    [int]$MemoryMb = 6000,
    [switch]$ResumeInterrupted,
    [switch]$CheckOnly
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$pythonPath = Join-Path (Get-Location) 'JMS-version/.solver_env/Scripts/python.exe'
$arguments = @('-u','-X','utf8','JMS-version/tools/run_exact_paper_queue.py','--output',$Output,'--jobs',"$Jobs",'--workers',"$Workers",'--memory-mb',"$MemoryMb")
if ($ResumeInterrupted) { $arguments += '--resume-interrupted' }
if ($CheckOnly) { $arguments += '--check-only' }
& $pythonPath @arguments
if ($LASTEXITCODE -ne 0) { throw 'Exact queue requires review. Preserve attempts and inspect queue.json and console logs.' }
