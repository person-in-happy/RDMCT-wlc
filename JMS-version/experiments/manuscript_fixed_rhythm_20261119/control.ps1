param([ValidateSet('Resume','Run','Status')][string]$Action='Resume')
$ErrorActionPreference='Stop'
$gapJms=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).Path
$gapSummary=Join-Path $gapJms 'results\manuscript_certified_gaps_physicalB_20261119_r2\report.json'
if ($Action -eq 'Status') {
    Get-Content -Raw -Encoding UTF8 -LiteralPath $gapSummary | ConvertFrom-Json |
        Select-Object grid_cells_completed,grid_cells_planned,completed_cells,planned_cells,selected
    return
}
$env:OMP_NUM_THREADS='1'
$env:MKL_NUM_THREADS='1'
$env:OPENBLAS_NUM_THREADS='1'
$gapPython='G:\conda\envs\a3cenv\python.exe'
$gapProcesses=@(Get-CimInstance Win32_Process -Filter "Name='python.exe'")
$gapEntries=@(
    @{File=(Join-Path $PSScriptRoot 'primary_only.py'); Extra=@()},
    @{File=(Join-Path $PSScriptRoot 'certify.py'); Extra=@()},
    @{File=(Join-Path $gapJms 'review\manuscript_certified_gaps_20261119\publish.py'); Extra=@('--watch')}
)
foreach ($gapEntry in $gapEntries) {
    $gapFile=(Resolve-Path -LiteralPath $gapEntry.File).Path
    $gapAlready=@($gapProcesses | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($gapFile) -and $_.CommandLine -notmatch ' --job ' })
    if ($gapAlready.Count -eq 0) {
        Start-Process -FilePath $gapPython -WindowStyle Normal -WorkingDirectory (Split-Path $gapJms -Parent) -ArgumentList (@('-B','-X','utf8','-u',$gapFile)+$gapEntry.Extra)
    }
}
