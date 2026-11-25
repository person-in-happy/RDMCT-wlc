param([string]$Python='G:/conda/python.exe')
& $Python -B -u -X utf8 (Join-Path $PSScriptRoot 'run.py')
exit $LASTEXITCODE
