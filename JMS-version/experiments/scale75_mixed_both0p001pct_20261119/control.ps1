param(
    [ValidateSet('Run','Resume','Status','Verify')][string]$Action='Status',
    [ValidateSet('primary','first','final')][string]$PausePhase='primary',
    [ValidateRange(0,500)][int]$PauseAfter=0,
    [string]$Python='G:\conda\python.exe'
)
$ErrorActionPreference = 'Stop'
$phases = if ($Action -in @('Run','Resume')) { @('primary','first','final','certify') } else { @($Action.ToLowerInvariant()) }
foreach ($phase in $phases) {
    $runArgs = @('-B','-X','utf8','-u',(Join-Path $PSScriptRoot 'run_equal_gaps.py'),$phase)
    if ($PauseAfter -and $phase -eq $PausePhase) { $runArgs += @('--pause-after',$PauseAfter) }
    Write-Host "75 mixed wafers | makespan gap 0.001% | chamber idle gap 0.001% | $phase"
    & $Python @runArgs
    if ($LASTEXITCODE -eq 20) { Write-Host 'Paused. Use -Action Resume to continue from the last saved step.'; return }
    if ($LASTEXITCODE -ne 0) { throw "75-wafer $phase exited with code $LASTEXITCODE" }
}
