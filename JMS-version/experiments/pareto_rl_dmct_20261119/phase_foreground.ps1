param([Parameter(Mandatory)][string]$OutputName,[int]$Seconds=150,[string]$SourceName)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$Host.UI.RawUI.WindowTitle = "S1 active topology search | $OutputName"
$experimentPython = 'G:\conda\envs\a3cenv\python.exe'
$experimentRuns = Join-Path $PSScriptRoot 'runs'
$experimentOut = Join-Path $experimentRuns $OutputName
Start-Transcript -Path (Join-Path $experimentRuns ("{0}_{1}.log" -f $OutputName,(Get-Date -Format 'yyyyMMdd_HHmmss')))
try {
    if ($SourceName) {
        $sourceArchive = Join-Path $experimentRuns $SourceName
        & $experimentPython -B -X utf8 -u (Join-Path $PSScriptRoot 'split_refinement.py') $sourceArchive $experimentOut --seconds $Seconds
    } else {
        & $experimentPython -B -X utf8 -u (Join-Path $PSScriptRoot 'active_phase.py') $experimentOut --seconds $Seconds
    }
    if ($LASTEXITCODE -ne 0) { throw 'Active phase search failed. See this transcript.' }
} finally {
    Stop-Transcript
}
