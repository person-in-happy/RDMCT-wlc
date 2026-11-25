$ErrorActionPreference = 'Stop'
$pythonPath = 'G:/conda/python.exe'
$stageFile = Join-Path $PSScriptRoot 'prepare.py'
$resultPath = Join-Path (Split-Path (Split-Path $PSScriptRoot -Parent) -Parent) 'results/table3_mixed16_20261125'
[void](New-Item -ItemType Directory -Path $resultPath -Force)
$statusPath = Join-Path $resultPath 'preparation_progress.json'
$elapsedBefore = 0
if (Test-Path -LiteralPath $statusPath) { $elapsedBefore = (Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json).elapsed_seconds }
$timeAtStart = Get-Date
$targetFile = Join-Path $resultPath 'prepared/primary.json'
if (-not (Test-Path -LiteralPath $targetFile)) {
    $previous = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($stageFile, [StringComparison]::OrdinalIgnoreCase) -ge 0 })
    if ($previous.Count -gt 0) { $worker = Get-Process -Id $previous[0].ProcessId }
    else { $worker = Start-Process -FilePath $pythonPath -NoNewWindow -PassThru -ArgumentList @('-B','-u','-X','utf8',$stageFile) }
    while (-not $worker.HasExited) {
        $wall = [int]($elapsedBefore + ((Get-Date)-$timeAtStart).TotalSeconds)
        $remaining = [Math]::Max(5,180-$wall)
        $state = [ordered]@{stage='constructive, SPBS and full native validation';cells_completed=0;cells_expected=9;failed=0;elapsed_seconds=$wall;estimated_stage_total_seconds=($wall+$remaining);estimated_stage_remaining_seconds=$remaining;estimated_grid_total_seconds=$null;estimate_basis='Eight-wafer initialization about 52s; plan 180s for 16-wafer original row validation. Tight 16-wafer grid has no observed completion time.';worker=$worker.Id}
        $state | ConvertTo-Json | Set-Content -LiteralPath "$statusPath.tmp" -Encoding UTF8
        Move-Item -Force -LiteralPath "$statusPath.tmp" -Destination $statusPath
        Write-Host "16-mixed 0/9; failures 0; initializing, elapsed ${wall}s, stage ETA ${remaining}s; tight grid ETA unknown."
        Start-Sleep -Seconds 5
        $worker.Refresh()
    }
}
if (-not (Test-Path -LiteralPath $targetFile)) { throw '16-wafer SPBS or native validation failed.' }
Write-Host "Validated the 16-wafer SPBS endpoint."
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'stream.py')) {
    & $pythonPath -B -u -X utf8 (Join-Path $PSScriptRoot 'stream.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $progress = Join-Path $resultPath 'progress.json'
    if ((Test-Path -LiteralPath $progress) -and ((Get-Content -Raw -LiteralPath $progress | ConvertFrom-Json).completed -eq 9)) {
        & $pythonPath -B -u -X utf8 (Join-Path $PSScriptRoot 'publish.py')
    }
    exit $LASTEXITCODE
}
