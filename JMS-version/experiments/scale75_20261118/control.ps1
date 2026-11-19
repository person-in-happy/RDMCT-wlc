param(
    [ValidateSet('Run','Resume','Status','Verify','AuditModel')][string]$Action='Status',
    [string]$Campaign,
    [ValidateRange(0,20)][int]$PauseAfterGroups=0,
    [string]$Python='G:\conda\envs\a3cenv\python.exe'
)
$ErrorActionPreference='Stop'
if (-not $Campaign) { $Campaign=Join-Path $PSScriptRoot '..\..\results\scale75_mixed_D_20261118_r1' }
function Invoke-OriginalModelAudit {
    $auditCase=(Resolve-Path -LiteralPath $Campaign).Path
    $auditScript=Join-Path $PSScriptRoot 'audit\check_model.py'
    if (Test-Path -LiteralPath (Join-Path $auditCase 'original_row_audit\certificate.json')) {
        & $Python -B -X utf8 -u $auditScript --campaign $auditCase
    } else {
        $auditLog=Join-Path $auditCase ("original_audit_" + [DateTime]::UtcNow.Ticks + ".log")
        & $Python -B -X utf8 -u $auditScript --campaign $auditCase 2>&1 | Tee-Object -FilePath $auditLog
    }
    if ($LASTEXITCODE -ne 0) { throw 'Original model verification failed' }
}
if ($Action -eq 'AuditModel') {
    Invoke-OriginalModelAudit
    return
}
$scaleArgs=@('-B','-X','utf8','-u',(Join-Path $PSScriptRoot 'run.py'),$Action.ToLowerInvariant())
if ($Campaign) { $scaleArgs+=@('--campaign',$Campaign) }
if ($PauseAfterGroups) { $scaleArgs+=@('--pause-after-groups',$PauseAfterGroups) }
& $Python @scaleArgs
if ($LASTEXITCODE -ne 0) { throw "75-wafer experiment exited with code $LASTEXITCODE" }
if (Test-Path -LiteralPath (Join-Path $Campaign 'summary.json')) {
    if ($Action -eq 'Status') {
        $certified=Test-Path -LiteralPath (Join-Path $Campaign 'original_row_audit\certificate.json')
        Write-Output "Original model certificate present: $certified"
    } else {
        Invoke-OriginalModelAudit
    }
}
