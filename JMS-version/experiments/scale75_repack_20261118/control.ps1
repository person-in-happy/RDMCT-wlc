param(
    [ValidateSet('Run','Resume','Verify','Status')][string]$Action='Status',
    [string]$Campaign,
    [ValidateRange(0,500)][int]$PauseAfterWindows=0,
    [string]$Python='G:\conda\python.exe'
)
$ErrorActionPreference='Stop'
$repackArgs=@('-B','-X','utf8','-u',(Join-Path $PSScriptRoot 'improve.py'),$Action.ToLowerInvariant())
if ($Campaign) { $repackArgs+=@('--out',$Campaign) }
if ($PauseAfterWindows) { $repackArgs+=@('--pause-after-windows',$PauseAfterWindows) }
& $Python @repackArgs
if ($LASTEXITCODE -ne 0) { throw "75-wafer repacking exited with code $LASTEXITCODE" }
