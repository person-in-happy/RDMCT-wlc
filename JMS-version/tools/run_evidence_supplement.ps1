# Run in this visible terminal. Never launches a background queue.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('fixed','mode24','scale32','gantt16','rhythm','cleaning','doe','ood')]
    [string]$Suite,
    [Parameter(Mandatory=$true)][string]$Output,
    [ValidateSet('Start','Prepare','Preflight','Run','Resume','Audit','Status')]
    [string]$Action = 'Prepare',
    # NEW campaigns require an explicit positive MemoryMb; no auto allocation.
    # Omitted on existing campaigns reuses the frozen memory budget.
    [ValidateRange(0,1000000)][int]$MemoryMb = 0,
    [ValidateRange(0,64)][int]$Jobs = 0,
    [string]$Python = 'G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
Push-Location -LiteralPath $repoRoot
try {
    if ($Action -notin @('Start','Prepare') -and ($MemoryMb -or $Jobs)) {
        throw 'Resources are frozen at Prepare. Omit MemoryMb/Jobs for later actions.'
    }
    $invokeArgs = @('-X','utf8','-u','JMS-version/tools/fixed_evidence_supplement.py',
                    $Action.ToLowerInvariant(),'--suite',$Suite,'--campaign',$Output)
    if ($MemoryMb) { $invokeArgs += @('--memory-mb', "$MemoryMb") }
    if ($Jobs) { $invokeArgs += @('--jobs', "$Jobs") }
    & $Python @invokeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Supplement $Action failed. Inspect saved logs; do not continue to the next stage."
    }
}
finally { Pop-Location }
