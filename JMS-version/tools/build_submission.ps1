param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$paperRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$buildRoot = [IO.Path]::GetFullPath((Join-Path $paperRoot 'output/.build'))
if (-not $buildRoot.StartsWith($paperRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid build directory.' }
& $Python (Join-Path $PSScriptRoot 'build_submission.py')
if ($LASTEXITCODE -ne 0) { throw 'Submission build failed; diagnostic files retained in output/.build.' }
if (Test-Path -LiteralPath $buildRoot) { Remove-Item -LiteralPath $buildRoot -Recurse -Force }
