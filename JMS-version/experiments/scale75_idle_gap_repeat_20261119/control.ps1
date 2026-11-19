param(
    [ValidateSet('Run','Resume','Status','Verify')][string]$Action='Status',
    [string]$GapPercent='0.000000001',
    [string]$Campaign,
    [ValidateSet('first','final')][string]$PausePhase='first',
    [ValidateRange(0,500)][int]$PauseAfter=0,
    [string]$Python='G:\conda\python.exe'
)
$ErrorActionPreference='Stop'
$phases = if ($Action -in @('Run','Resume')) { @('first','final','certify') } else { @($Action.ToLowerInvariant()) }
foreach ($phase in $phases) {
    $runArgs = @('-B','-X','utf8','-u',(Join-Path $PSScriptRoot 'run_gap.py'),$phase,'--gap-percent',$GapPercent)
    if ($Campaign) { $runArgs += @('--out',$Campaign) }
    if ($PauseAfter -and $phase -eq $PausePhase) { $runArgs += @('--pause-after',$PauseAfter) }
    & $Python @runArgs
    if ($LASTEXITCODE -eq 20) { Write-Host 'Paused at the last saved step.'; return }
    if ($LASTEXITCODE -ne 0) { throw "75-wafer $phase exited with code $LASTEXITCODE" }
}
