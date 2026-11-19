# In the foreground press Ctrl+C to stop. Resume reuses complete grouping
# layers and rolling windows and checks hashes before skipping finished cases.
param(
    [ValidateSet('Run','Resume','Status','Verify','Figures','Report','Prepare')]
    [string]$Action = 'Run',
    [ValidateRange(1,3)][int]$Jobs = 2,
    [string]$OutputDirectory = '',
    [string]$PythonExe = 'G:\conda\python.exe'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonExe)) { $PythonExe = 'python' }
$entry = Join-Path $PSScriptRoot 'campaign.py'
$paramsForRun = @('-B','-X','utf8','-u',$entry,$Action.ToLowerInvariant(),'--jobs',"$Jobs")
if ($OutputDirectory) { $paramsForRun += @('--output',$OutputDirectory) }
& $PythonExe @paramsForRun
exit $LASTEXITCODE
