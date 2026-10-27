[CmdletBinding()]
param(
    [string]$Python = 'G:\conda\envs\a3cenv\python.exe',
    [string]$Output = 'JMS-version/results/paper_optimality_foreground_20261022',
    [int]$Jobs = 2,
    [double]$MemoryMb = 6000,
    [switch]$ResumeInterrupted
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
$arguments = @('-u','-X','utf8','JMS-version/tools/continue_paper_optimality.py','--output',$Output,'--jobs',"$Jobs",'--memory-mb',"$MemoryMb")
if ($ResumeInterrupted) { $arguments += '--resume-interrupted' }
& $Python @arguments
if ($LASTEXITCODE -ne 0) { throw 'Optimality queue stopped with an error. Inspect its logs; do not delete prior attempts.' }
