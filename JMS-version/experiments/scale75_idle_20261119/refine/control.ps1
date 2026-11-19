param(
    [ValidateSet('Run','Resume','Verify','Status')][string]$Action='Status',
    [string]$Campaign,
    [ValidateRange(0,500)][int]$PauseAfter=0,
    [string]$Python='G:\conda\python.exe'
)
$ErrorActionPreference='Stop'
$idleArgs=@('-B','-X','utf8','-u',(Join-Path $PSScriptRoot 'extend.py'),$Action.ToLowerInvariant())
if ($Campaign) { $idleArgs+=@('--out',$Campaign) }
if ($PauseAfter) { $idleArgs+=@('--pause-after',$PauseAfter) }
& $Python @idleArgs
if ($LASTEXITCODE -ne 0) { throw "75-wafer idle refinement exited with code $LASTEXITCODE" }
