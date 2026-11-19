param(
    [ValidateSet('Run','Resume','Verify','Status')][string]$Action='Status',
    [string]$Campaign,
    [ValidateSet('first','final')][string]$PausePhase='first',
    [ValidateRange(0,500)][int]$PauseAfter=0,
    [string]$Python='G:\conda\python.exe'
)
$ErrorActionPreference='Stop'
$phases = if ($Action -in @('Run','Resume')) { @('first','final','certify') } else { @($Action.ToLowerInvariant()) }
foreach ($phase in $phases) {
    $caseArgs = @('-B','-X','utf8','-u',(Join-Path $PSScriptRoot 'rerun.py'),$phase)
    if ($Campaign) { $caseArgs += @('--out',$Campaign) }
    if ($PauseAfter -and $phase -eq $PausePhase) { $caseArgs += @('--pause-after',$PauseAfter) }
    & $Python @caseArgs
    if ($LASTEXITCODE -eq 20) { Write-Host 'Paused. Resume uses the last complete checkpoint.'; return }
    if ($LASTEXITCODE -ne 0) { throw "75-wafer stage $phase exited with code $LASTEXITCODE" }
}
