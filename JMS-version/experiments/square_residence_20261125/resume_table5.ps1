$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'paired_rerun.py'
$working = (Resolve-Path (Join-Path $PSScriptRoot '../../..')).Path
$argsForPython = @('-u', '-B', '-X', 'utf8', ('"' + $script + '"'))
Start-Process -FilePath 'G:/conda/envs/a3cenv/python.exe' -ArgumentList $argsForPython -WorkingDirectory $working -WindowStyle Normal
